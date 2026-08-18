"""FastAPI application factory and server entrypoint.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from netscan import __version__
from netscan.alerts.notify import send_alerts
from netscan.api.deps import AppState, get_state, init_state
from netscan.config import load_settings
from netscan.integrations import adguard, proxmox, truenas
from netscan.scanner import engine, tools

logger = logging.getLogger("netscan")


def setup_logging() -> None:
    from netscan.api.deps import _state

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if _state is not None:
        try:
            _state.settings.data_dir.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(_state.settings.data_dir / "netscan.log", encoding="utf-8"))
        except OSError:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def require_token(request: Request) -> None:
    """Global auth: only active when NETSCAN_API_TOKEN is set."""
    token = get_state().settings.api_token
    if not token:
        return
    provided = request.headers.get("x-api-key", "")
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        provided = provided or auth[7:]
    if provided != token:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


def _validate_network(network: str | None) -> None:
    """Reject scans against non-private CIDRs (the API must not be a scan oracle)."""
    if not network:
        return
    try:
        net = ipaddress.IPv4Network(network, strict=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Red inválida: {network}") from exc
    if not net.is_private:
        raise HTTPException(status_code=400, detail="Solo se permiten redes privadas (RFC1918)")


class ScanRequest(BaseModel):
    network: str | None = None
    full: bool | None = None


class TrustRequest(BaseModel):
    trusted: bool
    notes: str | None = None


def _run_scan_task(state: AppState, req: ScanRequest) -> None:
    """Blocking scan executed in a worker thread."""
    if not state.scan_lock.acquire(blocking=False):
        return
    try:
        result = engine.run_scan(
            cfg=state.settings.scan,
            network=req.network,
            full=req.full,
            progress=state.progress_callback,
        )
        alerts = state.store.record_scan(
            result,
            alert_on_new=state.settings.scan.alert_on_new_device,
            alert_on_down=state.settings.scan.alert_on_device_down,
        )
        send_alerts(alerts, state.settings.notify_urls)
        state.scan_progress = {"stage": "done", "done": 1, "total": 1}
    except Exception:
        logger.exception("Scan failed")
        state.scan_progress = {"stage": "error: fallo en el escaneo (ver netscan.log)", "done": 0, "total": 0}
    finally:
        state.scan_lock.release()


def _scheduler_loop(state: AppState) -> None:
    """Periodic re-scan when interval_minutes > 0."""
    while True:
        interval = state.settings.scan.interval_minutes
        if interval > 0:
            time.sleep(interval * 60)
            _run_scan_task(state, ScanRequest())
        else:
            time.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = init_state(load_settings())
    setup_logging()
    state.loop = asyncio.get_running_loop()
    threading.Thread(target=_scheduler_loop, args=(state,), daemon=True).start()
    logger.info("NetScan API v%s lista", __version__)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="NetScan API",
        version=__version__,
        lifespan=lifespan,
        dependencies=[Depends(require_token)],
    )
    cors_origins = load_settings().api_cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "X-API-Key", "Content-Type"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/capabilities")
    def capabilities() -> dict[str, object]:
        caps = get_state().capabilities()
        return {
            "capabilities": caps.as_dict(),
            "tools": {
                key: {"available": spec.available, "license": spec.license, "purpose": spec.purpose}
                for key, spec in tools.TOOLS.items()
            },
        }

    @app.post("/api/scans", status_code=202)
    def start_scan(req: ScanRequest) -> dict[str, str]:
        _validate_network(req.network)
        state = get_state()
        if state.scan_lock.locked():
            raise HTTPException(status_code=409, detail="Scan already in progress")
        threading.Thread(target=_run_scan_task, args=(state, req), daemon=True).start()
        return {"status": "started"}

    @app.get("/api/scans/latest")
    def latest_scan() -> dict[str, object]:
        record = get_state().store.last_scan()
        if not record:
            raise HTTPException(status_code=404, detail="No scans yet")
        return {
            "started_at": record.started_at.isoformat(),
            "result": json.loads(record.result_json),
        }

    @app.get("/api/scans/progress")
    def scan_progress() -> dict[str, object]:
        return get_state().scan_progress

    @app.websocket("/ws/progress")
    async def ws_progress(ws: WebSocket) -> None:
        state = get_state()
        token = state.settings.api_token
        if token and ws.query_params.get("token") != token:
            await ws.close(code=4401)
            return
        await ws.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        state.ws_clients.add(queue)
        try:
            await ws.send_text(json.dumps(state.scan_progress))
            while True:
                progress = await queue.get()
                await ws.send_text(json.dumps(progress))
        except WebSocketDisconnect:
            pass
        finally:
            state.ws_clients.discard(queue)

    @app.get("/api/devices")
    def list_devices() -> list[dict[str, object]]:
        return [d.model_dump() for d in get_state().store.list_devices()]

    @app.patch("/api/devices/{mac}")
    def update_device(mac: str, req: TrustRequest) -> dict[str, bool]:
        ok = get_state().store.set_device_trusted(mac, req.trusted, req.notes)
        if not ok:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"ok": True}

    @app.post("/api/devices/{mac}/wake")
    def wake_device(mac: str) -> dict[str, bool]:
        from netscan import wol

        try:
            wol.wake(mac)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.get("/api/alerts")
    def list_alerts(unacknowledged: bool = False) -> list[dict[str, object]]:
        return [a.model_dump() for a in get_state().store.list_alerts(unacknowledged)]

    @app.post("/api/alerts/{alert_id}/ack")
    def ack_alert(alert_id: int) -> dict[str, bool]:
        ok = get_state().store.acknowledge_alert(alert_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"ok": True}

    @app.get("/api/integrations/proxmox")
    def get_proxmox() -> list[dict[str, object]]:
        return proxmox.collect_all(get_state().settings.proxmox)

    @app.get("/api/integrations/truenas")
    def get_truenas() -> list[dict[str, object]]:
        return truenas.collect_all(get_state().settings.truenas)

    @app.get("/api/integrations/adguard")
    def get_adguard() -> list[dict[str, object]]:
        return adguard.collect_all(get_state().settings.adguard)

    @app.get("/api/overview")
    def overview() -> dict[str, object]:
        """One-shot aggregated payload for the dashboard."""
        state = get_state()
        devices = state.store.list_devices()
        last = state.store.last_scan()
        return {
            "version": __version__,
            "devices_total": len(devices),
            "devices_online": sum(1 for d in devices if d.online),
            "devices_untrusted": sum(1 for d in devices if not d.trusted),
            "alerts_unacknowledged": len(state.store.list_alerts(unacknowledged_only=True)),
            "last_scan": last.started_at.isoformat() if last else None,
            "capabilities": state.capabilities().as_dict(),
        }

    return app


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "netscan.api.app:create_app",
        factory=True,
        host=settings.api_host,
        port=settings.api_port,
    )


if __name__ == "__main__":
    main()
