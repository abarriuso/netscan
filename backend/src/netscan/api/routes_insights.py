"""Cross-source views: uptime/SLA, device profile & timeline, network map,
IP map, security posture and inventory export.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from netscan import insights
from netscan.api.deps import AppState, get_state
from netscan.models import ScanResult
from netscan.security import assess

router = APIRouter()


def _latest(state: AppState) -> dict[str, Any] | None:
    record = state.store.last_scan()
    if not record:
        return None
    return ScanResult.model_validate_json(record.result_json).model_dump(mode="json")


def _network(state: AppState, latest: dict[str, Any] | None) -> str | None:
    return (latest or {}).get("network") or state.network_cidr


@router.get("/api/uptime")
def uptime(hours: float = 24, slots: int = 48) -> dict[str, object]:
    """Availability of every device: 1h/24h/7d/30d windows + timeline slots."""
    state = get_state()
    return insights.uptime_report(
        state.store, state.live, hours=hours, slots=slots, interval_s=state.settings.scan.live_interval_s
    )


@router.get("/api/devices/{mac}/uptime")
def device_uptime(mac: str, hours: float = 24, slots: int = 96) -> dict[str, object]:
    state = get_state()
    report = insights.uptime_report(
        state.store,
        state.live,
        hours=hours,
        slots=slots,
        mac=mac,
        interval_s=state.settings.scan.live_interval_s,
    )
    if not report["devices"]:
        raise HTTPException(status_code=404, detail="Device not found")
    return {**report, "device": report["devices"][0]}


@router.get("/api/devices/{mac}/timeline")
def device_timeline(mac: str, limit: int = 200) -> dict[str, object]:
    state = get_state()
    if state.store.device_by_mac(mac) is None:
        raise HTTPException(status_code=404, detail="Device not found")
    events = state.store.device_events(mac=mac, limit=max(1, min(limit, 1000)))
    return {
        "mac": mac,
        "events": [
            {
                "at": e.created_at.isoformat(timespec="seconds"),
                "kind": e.kind,
                "detail": e.detail,
                "data": json.loads(e.data_json or "{}"),
            }
            for e in events
        ],
    }


@router.get("/api/devices/{mac}/profile")
def device_profile(mac: str) -> dict[str, object]:
    """Everything known about one device, crossed: inventory + latest scan
    (ports/versions, web UIs, TLS) + role inference + risk + live state."""
    state = get_state()
    record = state.store.device_by_mac(mac)
    if record is None:
        raise HTTPException(status_code=404, detail="Device not found")
    latest = _latest(state)
    scan_dev = next((d for d in (latest or {}).get("devices", []) if d.get("ip") == record.ip), None)
    findings = [
        f
        for f in (latest or {}).get("vulnerabilities", [])
        if re.sub(r"^https?://", "", f.get("matched_at", "")).split("/")[0].split(":")[0] == record.ip
    ]
    view = insights.device_view(record, scan_dev, state.gateway_ip, state.local_ip)
    risk = assess(
        {**record.model_dump(), "ports": view["ports"]},
        scan_dev,
        findings,
        conflict_macs=(scan_dev or {}).get("conflict_macs") or None,
    )
    live_row = None
    if state.live is not None:
        live_row = next((d for d in state.live.snapshot()["devices"] if d["mac"] == mac), None)  # type: ignore[attr-defined]
    return {
        "device": record.model_dump(mode="json"),
        "classification": view["classification"],
        "mac_info": view["mac_info"],
        "ports": view["ports"],
        "http": (scan_dev or {}).get("http", []),
        "mdns_services": (scan_dev or {}).get("mdns_services", []),
        "findings": findings,
        "risk": risk,
        "live": live_row,
        "scan_time": (latest or {}).get("scan_time"),
    }


@router.get("/api/map")
def network_map() -> dict[str, object]:
    state = get_state()
    return insights.network_map(state.store, _latest(state), state.live, state.gateway_ip, state.local_ip)


@router.get("/api/ipmap")
def ip_map(network: str | None = None) -> dict[str, object]:
    state = get_state()
    cidr = network or _network(state, _latest(state))
    if not cidr:
        raise HTTPException(status_code=404, detail="No network known yet — run a scan first")
    try:
        return insights.ip_map(cidr, state.store, state.gateway_ip, state.local_ip, state.live)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/security")
def security() -> dict[str, object]:
    state = get_state()
    return insights.security_report(state.store, _latest(state), state.gateway_ip, state.local_ip)


@router.get("/api/export/devices")
def export_devices(format: str = "csv") -> Response:
    """Inventory export with role, risk and 24 h availability. csv | json."""
    state = get_state()
    latest = _latest(state)
    sec = {
        d["mac"]: d
        for d in insights.security_report(state.store, latest, state.gateway_ip, state.local_ip)["devices"]
    }
    up = {
        d["mac"]: d
        for d in insights.uptime_report(
            state.store, state.live, hours=24, slots=6, interval_s=state.settings.scan.live_interval_s
        )["devices"]
    }
    rows = []
    for record in state.store.list_devices():
        s = sec.get(record.mac, {})
        u = up.get(record.mac, {}).get("windows", {}).get("24h", {})
        try:
            ports = ",".join(str(p["port"]) for p in json.loads(record.open_ports_json or "[]"))
        except (ValueError, TypeError, KeyError):
            ports = ""
        rows.append(
            {
                "ip": record.ip,
                "mac": record.mac,
                "hostname": record.hostname,
                "mdns_name": record.mdns_name,
                "vendor": record.vendor,
                "role": s.get("role", ""),
                "os_guess": record.os_guess,
                "trusted": record.trusted,
                "online": record.online,
                "first_seen": record.first_seen.isoformat(timespec="seconds"),
                "last_seen": record.last_seen.isoformat(timespec="seconds"),
                "latency_ms": record.last_latency_ms,
                "jitter_ms": record.jitter_ms,
                "packet_loss_pct": record.packet_loss_pct,
                "quality_0_100": record.quality,
                "availability_24h_pct": u.get("availability_pct"),
                "risk_score_0_100": s.get("score"),
                "risk_level": s.get("level"),
                "open_tcp_ports": ports,
                "notes": record.notes,
            }
        )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if format == "json":
        return Response(
            json.dumps(rows, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="netscan-devices-{stamp}.json"'},
        )
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["ip"])
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="netscan-devices-{stamp}.csv"'},
    )
