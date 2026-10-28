"""Event feed (REST + WebSocket) and the Prometheus exposition.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from netscan import insights
from netscan.api.deps import get_state
from netscan.events import bus

router = APIRouter()


@router.get("/api/events")
def list_events(since: int = 0, limit: int = 500, sources: str = "") -> dict[str, object]:
    """Events after sequence number ``since`` (oldest first).

    ``dropped`` > 0 means the ring buffer (capacity ``events.bus.capacity``)
    overwrote that many events between your ``since`` and the oldest one
    still buffered.
    """
    wanted = {s.strip() for s in sources.split(",") if s.strip()} or None
    return bus.since(since, limit=limit, sources=wanted)


@router.get("/api/events/stats")
def event_stats() -> dict[str, object]:
    return bus.stats()


@router.websocket("/ws/events")
async def ws_events(ws: WebSocket) -> None:
    """Live event stream. ``?since=N`` replays the buffered events after N
    first, so a reconnecting terminal has no hole in its scrollback."""
    from netscan.api.app import _client_ip, _rate_limited, _request_guard

    state = get_state()
    token = state.settings.api_token
    # The HTTP middleware doesn't see WebSockets: without this, any website
    # could read the feed (scanned hosts, API calls, commands) cross-origin.
    if _request_guard(state, "WEBSOCKET", ws.headers):
        await ws.close(code=4403)
        return
    if token and not secrets.compare_digest(ws.query_params.get("token", ""), token):
        await ws.close(code=4429 if _rate_limited(state, _client_ip(ws)) else 4401)
        return
    await ws.accept()
    try:
        since = int(ws.query_params.get("since", "0"))
    except ValueError:
        since = 0
    queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
    state.event_clients.add(queue)
    try:
        backlog = bus.since(since, limit=1000 if since else 300)
        await ws.send_text(
            json.dumps({"type": "hello", "last_seq": backlog["last_seq"], "dropped": backlog["dropped"]})
        )
        for event in backlog["events"]:
            await ws.send_text(json.dumps(event))
        last_sent = backlog["events"][-1]["seq"] if backlog["events"] else since
        while True:
            event = await queue.get()
            if event["seq"] <= last_sent:
                continue  # already sent as part of the backlog
            if event["seq"] > last_sent + 1 and last_sent:
                # Our queue overflowed: tell the client so it can show a gap.
                gap = bus.since(last_sent, limit=1000)
                for missed in gap["events"]:
                    if missed["seq"] < event["seq"]:
                        await ws.send_text(json.dumps(missed))
            await ws.send_text(json.dumps(event))
            last_sent = event["seq"]
    except WebSocketDisconnect:
        pass
    except Exception:
        with contextlib.suppress(Exception):
            await ws.close()
    finally:
        state.event_clients.discard(queue)


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics() -> PlainTextResponse:
    """Prometheus text exposition (scrape it from Grafana/Prometheus).

    Units follow Prometheus conventions: seconds and ratios (0-1).
    """
    state = get_state()
    uptime = None
    try:
        uptime = insights.uptime_report(
            state.store, state.live, hours=24, slots=6, interval_s=state.settings.scan.live_interval_s
        )
    except Exception:
        uptime = None
    return PlainTextResponse(insights.prometheus(state, uptime), media_type="text/plain; version=0.0.4")
