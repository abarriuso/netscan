"""FastAPI application factory and server entrypoint.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import secrets
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from netscan import __version__, system
from netscan.alerts.notify import send_alerts
from netscan.api.deps import AppState, get_state, init_state
from netscan.config import (
    AdGuardInstance,
    CustomInstance,
    PiholeInstance,
    ProxmoxInstance,
    TrueNASInstance,
    load_settings,
)
from netscan.integrations import adguard, pihole, proxmox, truenas
from netscan.models import ScanResult
from netscan.scanner import engine, speed, tools

logger = logging.getLogger("netscan")

# Maps an integration "kind" string to the Pydantic model that validates its
# config — used by the settings CRUD endpoints below for both kinds of
# integration (YAML-defined, read-only) and DB-defined (editable).
KIND_MODELS: dict[str, type] = {
    "proxmox": ProxmoxInstance,
    "truenas": TrueNASInstance,
    "adguard": AdGuardInstance,
    "pihole": PiholeInstance,
    "custom": CustomInstance,
}
# Fields that hold a credential — masked in list responses, and an update
# that resends the mask (or leaves the field out) keeps the stored value
# instead of overwriting it with the mask string.
_SECRET_FIELDS: dict[str, set[str]] = {
    "proxmox": {"token_secret"},
    "truenas": {"api_key"},
    "adguard": {"password"},
    "pihole": {"password"},
    "custom": set(),
}
_SECRET_MASK = "••••••••"


def _redact_config(kind: str, config: dict[str, object]) -> dict[str, object]:
    redacted = dict(config)
    for field in _SECRET_FIELDS.get(kind, ()):
        if redacted.get(field):
            redacted[field] = _SECRET_MASK
    return redacted


def _merge_config_for_update(
    kind: str, existing: dict[str, object], incoming: dict[str, object]
) -> dict[str, object]:
    merged = dict(existing)
    merged.update(incoming)
    for field in _SECRET_FIELDS.get(kind, ()):
        if merged.get(field) in (None, "", _SECRET_MASK):
            merged[field] = existing.get(field, "")
    return merged


def _db_instances(state: AppState, kind: str, model_cls: type) -> list:
    """Enabled DB-managed instances of one kind, validated + deserialized."""
    out = []
    for row in state.store.list_integrations(kind=kind):
        if not row.enabled:
            continue
        try:
            out.append(model_cls(name=row.name, **json.loads(row.config_json)))
        except Exception:
            logger.warning("Integración %s (id=%s) tiene config inválida, se omite", kind, row.id)
    return out


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


def _token_ok(headers, token: str) -> bool:
    """Check X-API-Key / Bearer against the configured token (timing-safe)."""
    provided = headers.get("x-api-key", "")
    auth = headers.get("authorization", "")
    if auth.startswith("Bearer "):
        provided = provided or auth[7:]
    return secrets.compare_digest(provided, token)


# Basic brute-force throttle for the auth endpoints: a handful of failed
# attempts per client IP within a short window trips a 429 cooldown. This is
# an in-memory, single-process limiter — good enough for a homelab box, not
# a substitute for a real WAF/reverse-proxy rate limiter under heavier load.
_AUTH_FAIL_WINDOW_S = 60.0
_AUTH_FAIL_MAX = 10


def _client_ip(request_or_ws) -> str:
    client = request_or_ws.client
    return client.host if client else "unknown"


def _rate_limited(state: AppState, client_ip: str) -> bool:
    """Record a failed-auth attempt for ``client_ip``; True if now throttled."""
    now = time.time()
    bucket = state.auth_failures[client_ip]
    bucket.append(now)
    while bucket and now - bucket[0] > _AUTH_FAIL_WINDOW_S:
        bucket.popleft()
    return len(bucket) > _AUTH_FAIL_MAX


def _redact_db_url(url: str) -> str:
    """Strip any embedded credentials (user:pass@) from a DB URL.

    ``database_url`` can be a Postgres/MySQL DSN with a password in it
    (``postgresql://user:secret@host/db``); that must never be echoed back
    over the API (``/api/system``), even to an authenticated client.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if "@" not in parts.netloc:
        return url
    userinfo, _, hostport = parts.netloc.rpartition("@")
    if ":" not in userinfo:
        # No password embedded (bare "user@host") — nothing to redact.
        return url
    user = userinfo.split(":", 1)[0]
    redacted_netloc = f"{user}:***@{hostport}" if user else f"***@{hostport}"
    return urlunsplit((parts.scheme, redacted_netloc, parts.path, parts.query, parts.fragment))


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
    only: str | None = None  # one of engine.ONLY_STAGES — launch a single tool


class TrustRequest(BaseModel):
    trusted: bool
    notes: str | None = None


class IntegrationCreateRequest(BaseModel):
    kind: str
    name: str
    enabled: bool = True
    config: dict[str, object] = Field(default_factory=dict)


class IntegrationUpdateRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    config: dict[str, object] | None = None


def _run_scan_task(state: AppState, req: ScanRequest) -> None:
    """Blocking scan executed in a worker thread."""
    if not state.scan_lock.acquire(blocking=False):
        return
    try:
        result = engine.run_scan(
            cfg=state.settings.scan,
            network=req.network,
            full=req.full,
            only=req.only,
            progress=state.progress_callback,
        )
        alerts = state.store.record_scan(
            result,
            alert_on_new=state.settings.scan.alert_on_new_device,
            alert_on_down=state.settings.scan.alert_on_device_down,
        )
        send_alerts(alerts, state.settings.notify_urls)
        state.scans_completed += 1
        state.last_scan_duration_s = result.duration_s
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
    )
    cors_origins = load_settings().api_cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "X-API-Key", "Content-Type"],
    )

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        """Global auth for HTTP (the WebSocket checks its own ?token=)."""
        state = get_state()
        state.requests_served += 1
        token = state.settings.api_token
        # Static assets and the SPA shell stay reachable without a token so the
        # dashboard can load and then prompt for it on the first API call.
        # Integration logos are exempted too: they're rendered via plain
        # <img src>, which can't attach an X-API-Key header, and a branding
        # image isn't sensitive the way the rest of /api is.
        path = request.url.path
        needs_auth = path.startswith(("/api", "/ws")) and not path.endswith("/logo")
        if token and needs_auth and not _token_ok(request.headers, token):
            from fastapi.responses import JSONResponse

            client_ip = _client_ip(request)
            if _rate_limited(state, client_ip):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many failed authentication attempts"},
                    headers={"Retry-After": str(int(_AUTH_FAIL_WINDOW_S))},
                )
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})
        return await call_next(request)

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

    @app.get("/api/logs")
    def tail_logs(lines: int = 200) -> dict[str, object]:
        """Last N lines of netscan.log, for the dashboard's live console panel."""
        lines = max(1, min(lines, 2000))
        log_path = get_state().settings.data_dir / "netscan.log"
        if not log_path.exists():
            return {"path": str(log_path), "lines": []}
        with open(log_path, encoding="utf-8", errors="replace") as f:
            tail = deque(f, maxlen=lines)
        return {"path": str(log_path), "lines": [line.rstrip("\n") for line in tail]}

    @app.post("/api/scans", status_code=202)
    def start_scan(req: ScanRequest) -> dict[str, str]:
        _validate_network(req.network)
        if req.only is not None and req.only not in engine.ONLY_STAGES:
            raise HTTPException(
                status_code=400,
                detail=f"only debe ser uno de: {', '.join(sorted(engine.ONLY_STAGES))}",
            )
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
        # Re-validate through the model instead of a raw json.loads: a scan
        # stored before a field existed (e.g. HttpInfo.tech, added this
        # session) would otherwise come back without it, and the frontend
        # assuming the current shape crashes on `undefined.length`.
        # model_validate backfills any such field's default.
        result = ScanResult.model_validate_json(record.result_json)
        return {
            "started_at": record.started_at.isoformat(),
            "result": result.model_dump(mode="json"),
        }

    @app.get("/api/scans/progress")
    def scan_progress() -> dict[str, object]:
        return get_state().scan_progress

    @app.websocket("/ws/progress")
    async def ws_progress(ws: WebSocket) -> None:
        state = get_state()
        token = state.settings.api_token
        if token and not secrets.compare_digest(ws.query_params.get("token", ""), token):
            if _rate_limited(state, _client_ip(ws)):
                await ws.close(code=4429)
            else:
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
        state = get_state()
        return proxmox.collect_all(state.settings.proxmox + _db_instances(state, "proxmox", ProxmoxInstance))

    @app.get("/api/integrations/truenas")
    def get_truenas() -> list[dict[str, object]]:
        state = get_state()
        return truenas.collect_all(state.settings.truenas + _db_instances(state, "truenas", TrueNASInstance))

    @app.get("/api/integrations/adguard")
    def get_adguard() -> list[dict[str, object]]:
        state = get_state()
        return adguard.collect_all(state.settings.adguard + _db_instances(state, "adguard", AdGuardInstance))

    @app.get("/api/integrations/pihole")
    def get_pihole() -> list[dict[str, object]]:
        state = get_state()
        return pihole.collect_all(state.settings.pihole + _db_instances(state, "pihole", PiholeInstance))

    @app.get("/api/integrations/custom")
    def get_custom() -> list[dict[str, object]]:
        """Bookmark tiles: no data API, just a cheap up/down HTTP HEAD check."""
        state = get_state()
        out: list[dict[str, object]] = []
        for row in state.store.list_integrations(kind="custom"):
            if not row.enabled:
                continue
            try:
                cfg = CustomInstance(name=row.name, **json.loads(row.config_json))
            except Exception:
                continue
            status = "down"
            try:
                resp = httpx.head(cfg.url, timeout=3.0, follow_redirects=True)
                status = "up" if resp.status_code < 500 else "down"
            except Exception:
                status = "down"
            out.append(
                {
                    "id": row.id,
                    "name": cfg.name,
                    "url": cfg.url,
                    "status": status,
                    "logo_url": f"/api/settings/integrations/{row.id}/logo" if row.logo_path else None,
                }
            )
        return out

    @app.get("/api/settings/integrations")
    def list_integration_settings() -> list[dict[str, object]]:
        """All configured integrations — YAML-defined (read-only) and
        DB-defined (editable from the dashboard), merged for the settings UI."""
        state = get_state()
        out: list[dict[str, object]] = []
        for kind, instances in (
            ("proxmox", state.settings.proxmox),
            ("truenas", state.settings.truenas),
            ("adguard", state.settings.adguard),
            ("pihole", state.settings.pihole),
        ):
            for inst in instances:
                config = _redact_config(kind, inst.model_dump(exclude={"name", "enabled"}))
                out.append(
                    {
                        "kind": kind,
                        "name": inst.name,
                        "enabled": inst.enabled,
                        "config": config,
                        "editable": False,
                    }
                )
        for row in state.store.list_integrations():
            out.append(
                {
                    "id": row.id,
                    "kind": row.kind,
                    "name": row.name,
                    "enabled": row.enabled,
                    "config": _redact_config(row.kind, json.loads(row.config_json)),
                    "logo_url": f"/api/settings/integrations/{row.id}/logo" if row.logo_path else None,
                    "editable": True,
                }
            )
        return out

    @app.post("/api/settings/integrations", status_code=201)
    def create_integration_setting(req: IntegrationCreateRequest) -> dict[str, object]:
        model_cls = KIND_MODELS.get(req.kind)
        if model_cls is None:
            raise HTTPException(status_code=400, detail=f"Tipo de integración desconocido: {req.kind}")
        try:
            validated = model_cls(name=req.name, **req.config)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Configuración inválida: {exc}") from exc
        config_dict = validated.model_dump(exclude={"name", "enabled"})
        row = get_state().store.create_integration(
            kind=req.kind, name=req.name, config_json=json.dumps(config_dict), enabled=req.enabled
        )
        return {
            "id": row.id,
            "kind": row.kind,
            "name": row.name,
            "enabled": row.enabled,
            "config": _redact_config(row.kind, config_dict),
        }

    @app.patch("/api/settings/integrations/{integration_id}")
    def update_integration_setting(integration_id: int, req: IntegrationUpdateRequest) -> dict[str, object]:
        store = get_state().store
        row = store.get_integration(integration_id)
        if not row:
            raise HTTPException(status_code=404, detail="Integración no encontrada")
        model_cls = KIND_MODELS[row.kind]
        config_json = None
        if req.config is not None:
            merged = _merge_config_for_update(row.kind, json.loads(row.config_json), req.config)
            try:
                validated = model_cls(name=req.name or row.name, **merged)
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"Configuración inválida: {exc}") from exc
            config_json = json.dumps(validated.model_dump(exclude={"name", "enabled"}))
        updated = store.update_integration(
            integration_id, name=req.name, config_json=config_json, enabled=req.enabled
        )
        assert updated is not None
        return {"id": updated.id, "kind": updated.kind, "name": updated.name, "enabled": updated.enabled}

    @app.delete("/api/settings/integrations/{integration_id}")
    def delete_integration_setting(integration_id: int) -> dict[str, bool]:
        store = get_state().store
        row = store.get_integration(integration_id)
        if row and row.logo_path:
            logo_file = get_state().settings.data_dir / row.logo_path
            logo_file.unlink(missing_ok=True)
        ok = store.delete_integration(integration_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Integración no encontrada")
        return {"ok": True}

    @app.post("/api/settings/integrations/{integration_id}/logo")
    async def upload_integration_logo(integration_id: int, file: UploadFile) -> dict[str, object]:
        store = get_state().store
        row = store.get_integration(integration_id)
        if not row:
            raise HTTPException(status_code=404, detail="Integración no encontrada")
        if row.kind != "custom":
            raise HTTPException(
                status_code=400, detail="El logo solo se puede subir para integraciones personalizadas"
            )
        allowed = {"image/png": ".png", "image/svg+xml": ".svg", "image/jpeg": ".jpg", "image/webp": ".webp"}
        ext = allowed.get(file.content_type or "")
        if not ext:
            raise HTTPException(
                status_code=415, detail="Formato de imagen no soportado (usa PNG, SVG, JPG o WEBP)"
            )
        data = await file.read()
        if len(data) > 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="El logo no puede superar 2MB")
        settings = get_state().settings
        logos_dir = settings.data_dir / "logos"
        logos_dir.mkdir(parents=True, exist_ok=True)
        # Old logo may have had a different extension — clear any prior file first.
        for old in logos_dir.glob(f"{integration_id}.*"):
            old.unlink(missing_ok=True)
        dest = logos_dir / f"{integration_id}{ext}"
        dest.write_bytes(data)
        store.update_integration(integration_id, logo_path=f"logos/{integration_id}{ext}")
        return {"ok": True, "logo_url": f"/api/settings/integrations/{integration_id}/logo"}

    @app.get("/api/settings/integrations/{integration_id}/logo")
    def get_integration_logo(integration_id: int):
        row = get_state().store.get_integration(integration_id)
        if not row or not row.logo_path:
            raise HTTPException(status_code=404, detail="Sin logo")
        full_path = get_state().settings.data_dir / row.logo_path
        if not full_path.is_file():
            raise HTTPException(status_code=404, detail="Archivo de logo no encontrado")
        from fastapi.responses import FileResponse

        return FileResponse(str(full_path))

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
            "metrics": state.store.metrics_summary(),
        }

    @app.get("/api/system")
    def system_status() -> dict[str, object]:
        """Full host + backend-process + frontend-build status."""
        state = get_state()
        snapshot = system.collect(state.frontend_dist)
        snapshot["server"] = {
            "version": __version__,
            "uptime_seconds": round(time.time() - state.started_at, 1),
            "requests_served": state.requests_served,
            "scans_completed": state.scans_completed,
            "last_scan_duration_s": state.last_scan_duration_s,
            "scan_in_progress": state.scan_lock.locked(),
            "ws_clients": len(state.ws_clients),
            "scheduler_interval_min": state.settings.scan.interval_minutes,
            "api_host": state.settings.api_host,
            "api_port": state.settings.api_port,
            "auth_enabled": bool(state.settings.api_token),
            "db_url": _redact_db_url(state.settings.db_url),
        }
        frontend = snapshot.get("frontend")
        if isinstance(frontend, dict):
            frontend["served_by_backend"] = state.frontend_dist is not None
        return snapshot

    @app.get("/api/status")
    def status() -> dict[str, object]:
        """Everything-in-one aggregate: overview + system + scanner + integrations health."""
        state = get_state()
        devices = state.store.list_devices()
        last = state.store.last_scan()
        integ = state.settings
        return {
            "version": __version__,
            "timestamp": datetime.now().isoformat(),
            "overview": {
                "devices_total": len(devices),
                "devices_online": sum(1 for d in devices if d.online),
                "devices_untrusted": sum(1 for d in devices if not d.trusted),
                "alerts_unacknowledged": len(state.store.list_alerts(unacknowledged_only=True)),
                "last_scan": last.started_at.isoformat() if last else None,
            },
            "metrics": state.store.metrics_summary(),
            "system": system.collect(state.frontend_dist),
            "server": {
                "uptime_seconds": round(time.time() - state.started_at, 1),
                "requests_served": state.requests_served,
                "scans_completed": state.scans_completed,
                "scan_in_progress": state.scan_lock.locked(),
                "progress": state.scan_progress,
            },
            "capabilities": state.capabilities().as_dict(),
            "integrations": {
                "proxmox": sum(1 for i in integ.proxmox if i.enabled),
                "truenas": sum(1 for i in integ.truenas if i.enabled),
                "adguard": sum(1 for i in integ.adguard if i.enabled),
                "notify_urls": len(integ.notify_urls),
            },
        }

    @app.get("/api/metrics/summary")
    def metrics_summary() -> dict[str, object]:
        return get_state().store.metrics_summary()

    @app.get("/api/devices/{mac}/metrics")
    def device_metrics(mac: str, limit: int = 100) -> dict[str, object]:
        samples = get_state().store.metric_samples(mac, limit=limit)
        return {
            "mac": mac,
            "samples": [
                {
                    "t": s.created_at.isoformat(),
                    "latency_ms": s.latency_ms,
                    "jitter_ms": s.jitter_ms,
                    "packet_loss_pct": s.packet_loss_pct,
                    "tcp_connect_avg_ms": s.tcp_connect_avg_ms,
                    "throughput_mbps": s.throughput_mbps,
                    "quality": s.quality,
                }
                for s in samples
            ],
        }

    @app.post("/api/devices/{mac}/speedtest")
    def device_speedtest(mac: str, throughput: bool = False) -> dict[str, object]:
        """Run an on-demand speed test against one known device."""
        state = get_state()
        record = state.store.device_by_mac(mac)
        if not record:
            raise HTTPException(status_code=404, detail="Device not found")
        import json as _json

        try:
            ports = [p.get("port") for p in _json.loads(record.open_ports_json) if p.get("port")]
        except (ValueError, AttributeError):
            ports = []
        from netscan.models import PortInfo

        metrics = speed.measure_device(
            record.ip,
            [PortInfo(port=p) for p in ports],
            count=state.settings.scan.speedtest_pings,
            ping_timeout=state.settings.scan.ping_timeout,
            throughput=throughput or state.settings.scan.use_throughput,
        )
        metrics.measured_at = datetime.now()
        state.store.record_speedtest(mac, metrics)
        return {"mac": mac, "ip": record.ip, "metrics": metrics.model_dump()}

    # --- Static dashboard (served when the frontend has been built) ---------- #
    from netscan.api.deps import _find_frontend_dist

    dist = _find_frontend_dist()
    if dist is not None:
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/", include_in_schema=False)
        def _spa_root() -> FileResponse:
            return FileResponse(str(dist / "index.html"))

        @app.get("/{full_path:path}", include_in_schema=False)
        def _spa_catchall(full_path: str) -> FileResponse:
            candidate = dist / full_path
            if candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(dist / "index.html"))

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
