"""FastAPI application factory and server entrypoint.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import logging.handlers
import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from netscan import __version__, events, system
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
from netscan.events import emit, fmt_ms
from netscan.integrations import adguard, pihole, proxmox, truenas
from netscan.models import ScanResult
from netscan.scanner import discovery, engine, speed, tools
from netscan.timeutil import iso, localize, now_iso

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

# API paths whose calls are not echoed to the event feed: the terminal's own
# polling fallback would otherwise fill the feed with itself.
_QUIET_PATHS = ("/api/events", "/api/health")

LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB per file
LOG_BACKUPS = 3


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
            logger.warning("Integration %s (id=%s) has an invalid config, skipping it", kind, row.id)
    return out


class _ConnectionResetFilter(logging.Filter):
    """Windows' Proactor event loop logs an ERROR with a traceback every time
    a browser drops a socket without a clean close (WinError 10054 — tab
    closed, page reloaded). It is harmless; report it as a debug event
    instead of an error in the log and the dashboard terminal."""

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        if isinstance(exc, ConnectionResetError):
            emit("api", "client connection reset by the browser (tab closed/reloaded) — harmless", "debug")
            return False
        return True


def setup_logging() -> None:
    """Console + rotating file (5 MiB x 3) + the event bus.

    The file used to grow forever and ``/api/logs`` re-read it whole on
    every poll. httpx's per-request INFO lines are silenced: HTTP probes are
    reported on the event feed with timings instead.
    """
    from netscan.api.deps import _state

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if _state is not None:
        try:
            _state.settings.data_dir.mkdir(parents=True, exist_ok=True)
            handlers.append(
                logging.handlers.RotatingFileHandler(
                    _state.settings.data_dir / "netscan.log",
                    maxBytes=LOG_MAX_BYTES,
                    backupCount=LOG_BACKUPS,
                    encoding="utf-8",
                )
            )
        except OSError:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    bus_handler = events.BusLogHandler(level=logging.WARNING)
    logging.getLogger().addHandler(bus_handler)
    for noisy in ("httpx", "httpcore", "zeroconf", "scapy.runtime"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    asyncio_logger = logging.getLogger("asyncio")
    if not any(isinstance(f, _ConnectionResetFilter) for f in asyncio_logger.filters):
        asyncio_logger.addFilter(_ConnectionResetFilter())


def _offered_token(headers) -> str:
    """The token a client presented (X-API-Key, else Bearer), or ''."""
    provided = headers.get("x-api-key", "")
    auth = headers.get("authorization", "")
    if auth.startswith("Bearer "):
        provided = provided or auth[7:]
    return provided


def _token_matches(provided: str, token: str) -> bool:
    """Timing-safe comparison. Bytes, because compare_digest raises on a
    non-ASCII str — a pasted token with a stray character was a 500."""
    return secrets.compare_digest(provided.encode(), token.encode())


def _token_ok(headers, token: str) -> bool:
    """Check X-API-Key / Bearer against the configured token (timing-safe)."""
    return _token_matches(_offered_token(headers), token)


# Basic brute-force throttle for the auth endpoints: a handful of failed
# attempts per client IP within a short window trips a 429 cooldown. This is
# an in-memory, single-process limiter — good enough for a homelab box, not
# a substitute for a real WAF/reverse-proxy rate limiter under heavier load.
# Only a wrong token counts as an attempt: a request carrying none (the
# dashboard's first load, before the token dialog) guesses nothing, and
# counting those locked the browser out before the user had typed a thing.
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
        raise HTTPException(status_code=400, detail=f"Invalid network: {network}") from exc
    if not net.is_private:
        raise HTTPException(status_code=400, detail="Only private networks are allowed (RFC 1918)")


def _tail(path, lines: int) -> list[str]:
    """Last ``lines`` lines of a text file, reading backwards in 64 KiB blocks."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        data = b""
        block = 65536
        while end > 0 and data.count(b"\n") <= lines:
            start = max(0, end - block)
            f.seek(start)
            data = f.read(end - start) + data
            end = start
    return [line.decode("utf-8", "replace") for line in data.splitlines()[-lines:]]


class ScanRequest(BaseModel):
    network: str | None = None
    full: bool | None = None
    only: str | None = None  # one of engine.ONLY_STAGES — launch a single tool


class TrustRequest(BaseModel):
    trusted: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class IntegrationCreateRequest(BaseModel):
    kind: str
    name: str
    enabled: bool = True
    config: dict[str, object] = Field(default_factory=dict)


class IntegrationUpdateRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    config: dict[str, object] | None = None


def _refresh_network_identity(state: AppState) -> None:
    """Gateway / own IP / CIDR, used by the map, the live monitor and IPAM."""
    try:
        cidr, local_ip, _iface = discovery.get_local_network()
        state.network_cidr = state.settings.scan.network or cidr
        state.local_ip = local_ip
    except OSError:
        pass
    state.gateway_ip = discovery.default_gateway()


def _run_scan_task(state: AppState, req: ScanRequest) -> None:
    """Blocking scan executed in a worker thread. The caller holds scan_lock."""
    state.scan_started_at = time.time()
    state.last_scan_error = None
    try:
        state.progress_callback("starting", 0, 0)
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
            alert_on_ports=state.settings.scan.alert_on_port_change,
        )
        sent = send_alerts(alerts, state.settings.notify_urls)
        if alerts:
            emit(
                "alert",
                f"{len(alerts)} alert(s) raised · {sent} notification(s) delivered to "
                f"{len(state.settings.notify_urls)} Apprise URL(s)",
            )
        state.scans_completed += 1
        state.last_scan_duration_s = result.duration_s
        if result.gateway_ip:
            state.gateway_ip = result.gateway_ip
            if state.live is not None:
                state.live.gateway_ip = result.gateway_ip  # type: ignore[attr-defined]
        state.progress_callback("done", 1, 1)
    except Exception as exc:
        logger.exception("Scan failed")
        state.scans_failed += 1
        # Surface the real reason (missing privileges, Npcap, bad CIDR...)
        # instead of a generic "see netscan.log".
        message = str(exc) or type(exc).__name__
        state.last_scan_error = message
        emit("scan", f"scan FAILED: {message}", "error")
        state.scan_progress = {"stage": f"error: {message}", "done": 0, "total": 0, "error": message}
        if state.loop:
            state.loop.call_soon_threadsafe(state._broadcast)
    finally:
        state.scan_started_at = None
        state.scan_lock.release()


def _start_scan_thread(state: AppState, req: ScanRequest) -> bool:
    """Acquire the scan lock *here* (not in the worker) so two concurrent
    requests cannot both be told "started" while one silently no-ops."""
    if not state.scan_lock.acquire(blocking=False):
        return False
    threading.Thread(target=_run_scan_task, args=(state, req), name="scan", daemon=True).start()
    return True


def _scheduler_loop(state: AppState) -> None:
    """Periodic re-scan every ``interval_minutes`` (0 = disabled).

    The schedule is anchored on the last scan in the DB, so restarting the
    server does not postpone the next scan by a whole interval; a fresh
    install (no scan yet) scans 15 s after start-up.
    """
    time.sleep(15)
    while True:
        interval = state.settings.scan.interval_minutes
        if interval <= 0:
            state.next_scheduled_scan = None
            time.sleep(30)
            continue
        last = state.store.last_scan()
        due = (last.started_at + timedelta(minutes=interval)) if last else datetime.now()
        state.next_scheduled_scan = due
        wait = (due - datetime.now()).total_seconds()
        if wait > 0:
            time.sleep(min(wait, 60))
            continue
        emit("scheduler", f"scheduled scan (every {interval} min) starting")
        if not _start_scan_thread(state, ScanRequest()):
            emit("scheduler", "scheduled scan skipped: another scan is running", "warning")
            time.sleep(60)
            continue
        time.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = init_state(load_settings())
    setup_logging()
    state.loop = asyncio.get_running_loop()
    _refresh_network_identity(state)
    emit(
        "system",
        f"NetScan API v{__version__} starting · pid {os.getpid()} · listening {state.settings.api_host}:"
        f"{state.settings.api_port} · auth {'token' if state.settings.api_token else 'OFF'} · "
        f"network {state.network_cidr} · this host {state.local_ip} · gateway {state.gateway_ip} · "
        f"privileged {'yes' if discovery.is_elevated() else 'no (ICMP sweep fallback for discovery)'}",
    )
    threading.Thread(target=_scheduler_loop, args=(state,), name="scheduler", daemon=True).start()
    if state.settings.scan.live_enabled:
        from netscan.live import LiveMonitor

        scan_cfg = state.settings.scan
        state.live = LiveMonitor(
            state.store,
            interval_s=scan_cfg.live_interval_s,
            ping_timeout=scan_cfg.ping_timeout,
            buffer=scan_cfg.live_buffer,
            max_devices=scan_cfg.live_max_devices,
            down_after=scan_cfg.live_down_after,
            alert_on_change=scan_cfg.alert_on_device_down,
            wan_targets=scan_cfg.live_wan_targets,
            gateway_ip=state.gateway_ip,
        )
        state.live.start()
    logger.info("NetScan API v%s ready", __version__)
    yield
    if state.live is not None:
        state.live.stop()  # type: ignore[attr-defined]
    emit("system", "NetScan API shutting down")


def _bookmark_status(cfg: CustomInstance) -> dict[str, object]:
    """Up/down + response time for a bookmark tile.

    TLS is not verified (homelab UIs are self-signed: they used to show as
    "down"), and a server that rejects HEAD (405/501) gets a GET instead.
    """
    start = time.perf_counter()
    try:
        with httpx.Client(timeout=4.0, follow_redirects=True, verify=False) as client:
            resp = client.head(cfg.url)
            if resp.status_code in (405, 501):
                resp = client.get(cfg.url)
        ms = round((time.perf_counter() - start) * 1000, 1)
        return {
            "status": "up" if resp.status_code < 500 else "down",
            "http_status": resp.status_code,
            "ms": ms,
        }
    except Exception as exc:
        return {"status": "down", "http_status": None, "ms": None, "error": f"{type(exc).__name__}: {exc}"}


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
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "X-API-Key", "Content-Type"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Last-resort handler so an unexpected error is a clean JSON 500 with a
        message the dashboard can display — not a bare, bodyless 500 the client
        can only render as 'system: 500'. HTTPException keeps its own status and
        detail (Starlette handles it before this); this only catches the rest.
        The real traceback goes to the server log, never to the client."""
        from fastapi.responses import JSONResponse

        logger.exception("Unhandled error in %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal server error ({type(exc).__name__}). Check the NetScan logs."},
        )

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        """Global auth for HTTP (the WebSockets check their own ?token=), plus
        one event per API call (method, path, status, duration, size) for the
        dashboard terminal."""
        state = get_state()
        state.requests_served += 1
        token = state.settings.api_token
        # Static assets and the SPA shell stay reachable without a token so the
        # dashboard can load and then prompt for it on the first API call.
        # Integration logos are exempted too, but only for GET: they're
        # rendered via plain <img src>, which can't attach an X-API-Key
        # header. The upload (POST) used to be exempt as well — anyone on the
        # LAN could replace a logo without the token.
        path = request.url.path
        is_logo_read = request.method == "GET" and path.endswith("/logo")
        needs_auth = (path.startswith(("/api", "/ws")) or path == "/metrics") and not is_logo_read
        if token and needs_auth and not _token_ok(request.headers, token):
            from fastapi.responses import JSONResponse

            client_ip = _client_ip(request)
            emit("api", f"{request.method} {path} → 401 (bad or missing token) from {client_ip}", "warning")
            if _offered_token(request.headers) and _rate_limited(state, client_ip):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many failed authentication attempts"},
                    headers={"Retry-After": str(int(_AUTH_FAIL_WINDOW_S))},
                )
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})
        start = time.perf_counter()
        response = await call_next(request)
        if (path.startswith("/api") and not path.startswith(_QUIET_PATHS)) or path == "/metrics":
            elapsed = (time.perf_counter() - start) * 1000
            size = response.headers.get("content-length")
            query = f"?{request.url.query}" if request.url.query else ""
            emit(
                "api",
                f"{request.method} {path}{query} → {response.status_code} · {fmt_ms(elapsed)}"
                + (f" · {int(size) / 1024:.1f} KiB" if size else ""),
                "debug" if response.status_code < 400 else "warning",
                method=request.method,
                path=path,
                status=response.status_code,
                ms=round(elapsed, 2),
                bytes=int(size) if size else None,
                client=_client_ip(request),
            )
        return response

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/capabilities")
    def capabilities() -> dict[str, object]:
        from netscan.scanner import icmp

        caps = get_state().capabilities()
        return {
            "capabilities": caps.as_dict(),
            "tools": {
                key: {
                    "available": bool(caps.tools.get(key)),
                    "license": spec.license,
                    "purpose": spec.purpose,
                }
                for key, spec in tools.TOOLS.items()
            },
            "runtime": {
                "icmp_backend": icmp.backend(),
                "privileged": discovery.is_elevated(),
                "discovery": "arp" if discovery.is_elevated() else "sweep",
            },
        }

    @app.get("/api/logs")
    def tail_logs(lines: int = 200) -> dict[str, object]:
        """Last N lines of netscan.log, for the dashboard's live console panel."""
        lines = max(1, min(lines, 2000))
        log_path = get_state().settings.data_dir / "netscan.log"
        if not log_path.exists():
            return {"path": str(log_path), "lines": []}
        return {"path": str(log_path), "lines": _tail(log_path, lines)}

    @app.post("/api/scans", status_code=202)
    def start_scan(req: ScanRequest) -> dict[str, str]:
        _validate_network(req.network)
        if req.only is not None and req.only not in engine.ONLY_STAGES:
            raise HTTPException(
                status_code=400,
                detail=f"only must be one of: {', '.join(sorted(engine.ONLY_STAGES))}",
            )
        state = get_state()
        if not _start_scan_thread(state, req):
            raise HTTPException(status_code=409, detail="Scan already in progress")
        mode = f"only:{req.only}" if req.only else ("full" if req.full else "quick")
        emit(
            "scan",
            f"scan requested from the dashboard · mode {mode}"
            + (f" · network {req.network}" if req.network else ""),
        )
        return {"status": "started"}

    @app.get("/api/scans/latest")
    def latest_scan() -> dict[str, object]:
        record = get_state().store.last_scan()
        if not record:
            raise HTTPException(status_code=404, detail="No scans yet")
        # Re-validate through the model instead of a raw json.loads: a scan
        # stored before a field existed (e.g. HttpInfo.tech) would otherwise
        # come back without it, and the frontend assuming the current shape
        # crashes on `undefined.length`. model_validate backfills defaults.
        result = ScanResult.model_validate_json(record.result_json)
        return {
            "started_at": iso(record.started_at),
            "result": localize(result.model_dump()),
        }

    @app.get("/api/scans/progress")
    def scan_progress() -> dict[str, object]:
        return get_state().scan_progress

    @app.get("/api/live")
    def live() -> dict[str, object]:
        st = get_state()
        if st.live is None:
            return {"series": [], "devices": [], "online": 0, "total": 0, "interval_s": 0, "enabled": False}
        return {**st.live.snapshot(), "enabled": True}  # type: ignore[attr-defined]

    @app.websocket("/ws/progress")
    async def ws_progress(ws: WebSocket) -> None:
        state = get_state()
        token = state.settings.api_token
        offered = ws.query_params.get("token", "")
        if token and not _token_matches(offered, token):
            if offered and _rate_limited(state, _client_ip(ws)):
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
        return [localize(d.model_dump()) for d in get_state().store.list_devices()]

    @app.patch("/api/devices/{mac}")
    def update_device(mac: str, req: TrustRequest) -> dict[str, bool]:
        store = get_state().store
        if req.trusted is not None:
            ok = store.set_device_trusted(mac, req.trusted, req.notes)
        elif req.notes is not None:
            ok = store.set_device_notes(mac, req.notes)
        else:
            raise HTTPException(status_code=422, detail="Nothing to update: send trusted and/or notes")
        if not ok:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"ok": True}

    @app.post("/api/devices/{mac}/wake")
    def wake_device(mac: str) -> dict[str, object]:
        from netscan import wol

        try:
            target = wol.wake(mac)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        emit("toolbox", f"Wake-on-LAN magic packet x3 → {mac} via UDP {target}:9")
        return {"ok": True, "broadcast": target}

    @app.get("/api/alerts")
    def list_alerts(unacknowledged: bool = False) -> list[dict[str, object]]:
        return [localize(a.model_dump()) for a in get_state().store.list_alerts(unacknowledged)]

    @app.post("/api/alerts/{alert_id}/ack")
    def ack_alert(alert_id: int) -> dict[str, bool]:
        ok = get_state().store.acknowledge_alert(alert_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"ok": True}

    @app.post("/api/alerts/ack-all")
    def ack_all_alerts() -> dict[str, int]:
        return {"acknowledged": get_state().store.acknowledge_all_alerts()}

    def _collect(kind: str, collector, instances: list) -> list[dict[str, object]]:
        start = time.perf_counter()
        out = collector(instances)
        for item in out:
            if item.get("error"):
                emit(
                    "integration",
                    f"{kind} '{item.get('name')}' ({item.get('host')}) failed: {item['error']}",
                    "warning",
                )
        if instances:
            emit(
                "integration",
                f"{kind}: {len(instances)} instance(s) polled in {fmt_ms((time.perf_counter() - start) * 1000)}",
                "debug",
            )
        return out

    @app.get("/api/integrations/proxmox")
    def get_proxmox() -> list[dict[str, object]]:
        state = get_state()
        return _collect(
            "proxmox",
            proxmox.collect_all,
            state.settings.proxmox + _db_instances(state, "proxmox", ProxmoxInstance),
        )

    @app.get("/api/integrations/truenas")
    def get_truenas() -> list[dict[str, object]]:
        state = get_state()
        return _collect(
            "truenas",
            truenas.collect_all,
            state.settings.truenas + _db_instances(state, "truenas", TrueNASInstance),
        )

    @app.get("/api/integrations/adguard")
    def get_adguard() -> list[dict[str, object]]:
        state = get_state()
        return _collect(
            "adguard",
            adguard.collect_all,
            state.settings.adguard + _db_instances(state, "adguard", AdGuardInstance),
        )

    @app.get("/api/integrations/pihole")
    def get_pihole() -> list[dict[str, object]]:
        state = get_state()
        return _collect(
            "pihole",
            pihole.collect_all,
            state.settings.pihole + _db_instances(state, "pihole", PiholeInstance),
        )

    @app.get("/api/integrations/custom")
    def get_custom() -> list[dict[str, object]]:
        """Bookmark tiles: no data API, just a cheap up/down HTTP check (in parallel)."""
        state = get_state()
        rows = []
        for row in state.store.list_integrations(kind="custom"):
            if not row.enabled:
                continue
            try:
                rows.append((row, CustomInstance(name=row.name, **json.loads(row.config_json))))
            except Exception:
                continue
        if not rows:
            return []
        with ThreadPoolExecutor(max_workers=min(8, len(rows))) as pool:
            statuses = list(pool.map(lambda item: _bookmark_status(item[1]), rows))
        return [
            {
                "id": row.id,
                "name": cfg.name,
                "url": cfg.url,
                **status,
                "logo_url": f"/api/settings/integrations/{row.id}/logo" if row.logo_path else None,
            }
            for (row, cfg), status in zip(rows, statuses, strict=True)
        ]

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
            raise HTTPException(status_code=400, detail=f"Unknown integration type: {req.kind}")
        try:
            validated = model_cls(name=req.name, **req.config)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid configuration: {exc}") from exc
        config_dict = validated.model_dump(exclude={"name", "enabled"})
        row = get_state().store.create_integration(
            kind=req.kind, name=req.name, config_json=json.dumps(config_dict), enabled=req.enabled
        )
        emit("integration", f"{req.kind} integration '{req.name}' added")
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
            raise HTTPException(status_code=404, detail="Integration not found")
        model_cls = KIND_MODELS[row.kind]
        config_json = None
        if req.config is not None:
            merged = _merge_config_for_update(row.kind, json.loads(row.config_json), req.config)
            try:
                validated = model_cls(name=req.name or row.name, **merged)
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"Invalid configuration: {exc}") from exc
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
            raise HTTPException(status_code=404, detail="Integration not found")
        return {"ok": True}

    @app.post("/api/settings/integrations/{integration_id}/logo")
    async def upload_integration_logo(integration_id: int, file: UploadFile) -> dict[str, object]:
        store = get_state().store
        row = store.get_integration(integration_id)
        if not row:
            raise HTTPException(status_code=404, detail="Integration not found")
        if row.kind != "custom":
            raise HTTPException(status_code=400, detail="A logo can only be uploaded for custom integrations")
        allowed = {"image/png": ".png", "image/svg+xml": ".svg", "image/jpeg": ".jpg", "image/webp": ".webp"}
        ext = allowed.get(file.content_type or "")
        if not ext:
            raise HTTPException(
                status_code=415, detail="Unsupported image format (use PNG, SVG, JPG or WEBP)"
            )
        data = await file.read()
        if len(data) > 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="The logo cannot be larger than 2 MB")
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
            raise HTTPException(status_code=404, detail="No logo")
        full_path = get_state().settings.data_dir / row.logo_path
        if not full_path.is_file():
            raise HTTPException(status_code=404, detail="Logo file not found")
        from fastapi.responses import FileResponse

        headers = {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"}
        return FileResponse(str(full_path), headers=headers)

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
            "devices_new_24h": sum(1 for d in devices if datetime.now() - d.first_seen < timedelta(hours=24)),
            "alerts_unacknowledged": len(state.store.list_alerts(unacknowledged_only=True)),
            "last_scan": iso(last.started_at) if last else None,
            "last_scan_duration_s": last.duration_s if last else None,
            "next_scan": iso(state.next_scheduled_scan) if state.next_scheduled_scan else None,
            "last_scan_error": state.last_scan_error,
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
            "scans_failed": state.scans_failed,
            "last_scan_duration_s": state.last_scan_duration_s,
            "last_scan_error": state.last_scan_error,
            "scan_in_progress": state.scan_lock.locked(),
            "ws_clients": len(state.ws_clients) + len(state.event_clients),
            "scheduler_interval_min": state.settings.scan.interval_minutes,
            "next_scan": iso(state.next_scheduled_scan) if state.next_scheduled_scan else None,
            "api_host": state.settings.api_host,
            "api_port": state.settings.api_port,
            "auth_enabled": bool(state.settings.api_token),
            "db_url": _redact_db_url(state.settings.db_url),
            "privileged": discovery.is_elevated(),
            "events": events.bus.stats(),
            "gateway_ip": state.gateway_ip,
            "local_ip": state.local_ip,
            "network": state.network_cidr,
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

        def count(kind: str, yaml_instances: list) -> int:
            return sum(1 for i in yaml_instances if i.enabled) + sum(
                1 for r in state.store.list_integrations(kind=kind) if r.enabled
            )

        return {
            "version": __version__,
            "timestamp": now_iso(),
            "overview": {
                "devices_total": len(devices),
                "devices_online": sum(1 for d in devices if d.online),
                "devices_untrusted": sum(1 for d in devices if not d.trusted),
                "alerts_unacknowledged": len(state.store.list_alerts(unacknowledged_only=True)),
                "last_scan": iso(last.started_at) if last else None,
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
                "proxmox": count("proxmox", integ.proxmox),
                "truenas": count("truenas", integ.truenas),
                "adguard": count("adguard", integ.adguard),
                "pihole": count("pihole", integ.pihole),
                "custom": sum(1 for r in state.store.list_integrations(kind="custom") if r.enabled),
                "notify_urls": len(integ.notify_urls),
            },
        }

    @app.get("/api/metrics/summary")
    def metrics_summary() -> dict[str, object]:
        return get_state().store.metrics_summary()

    @app.get("/api/metrics/history")
    def metrics_history(limit: int = 200) -> dict[str, object]:
        return {"points": get_state().store.metrics_history(limit=limit)}

    @app.get("/api/scans/history")
    def scan_history(limit: int = 100) -> dict[str, object]:
        return {"scans": get_state().store.scan_history(limit=limit)}

    @app.get("/api/devices/{mac}/metrics")
    def device_metrics(mac: str, limit: int = 100) -> dict[str, object]:
        samples = get_state().store.metric_samples(mac, limit=limit)
        return {
            "mac": mac,
            "samples": [
                {
                    "t": iso(s.created_at),
                    "latency_ms": s.latency_ms,
                    "jitter_ms": s.jitter_ms,
                    "packet_loss_pct": s.packet_loss_pct,
                    "tcp_connect_avg_ms": s.tcp_connect_avg_ms,
                    "throughput_mbps": s.throughput_mbps,
                    "quality": s.quality,
                    "source": s.source,
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
        try:
            ports = [p.get("port") for p in json.loads(record.open_ports_json) if p.get("port")]
        except (ValueError, AttributeError):
            ports = []
        from netscan.models import PortInfo

        emit(
            "speed",
            f"on-demand speed test {record.ip} · {state.settings.scan.speedtest_pings} echoes · {len(ports)} known ports",
        )
        metrics = speed.measure_device(
            record.ip,
            [PortInfo(port=p) for p in ports],
            count=state.settings.scan.speedtest_pings,
            ping_timeout=state.settings.scan.ping_timeout,
            throughput=throughput or state.settings.scan.use_throughput,
        )
        metrics.measured_at = datetime.now()
        state.store.record_speedtest(mac, metrics)
        emit("speed", f"speed test {record.ip}: quality {metrics.quality}/100")
        return {"mac": mac, "ip": record.ip, "metrics": localize(metrics.model_dump())}

    from netscan.api import routes_events, routes_insights, routes_toolbox

    app.include_router(routes_events.router)
    app.include_router(routes_insights.router)
    app.include_router(routes_toolbox.router)

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

        dist_root = dist.resolve()

        @app.get("/{full_path:path}", include_in_schema=False)
        def _spa_catchall(full_path: str) -> FileResponse:
            # Resolve and confine to dist: an absolute path ("//etc/passwd") or
            # "../" segments would otherwise escape the bundle directory.
            candidate = (dist_root / full_path.lstrip("/\\")).resolve()
            if candidate.is_relative_to(dist_root) and candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(dist_root / "index.html"))

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
