"""Cross-source analytics: uptime/SLA, outages, network map, IP map,
security posture and the Prometheus exposition.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Everything here is derived at request time from what the scanner, the live
monitor and the inventory already store — no extra probing. The numbers
carry their definitions:

* **availability %** = probes answered / probes sent in the window
  (live monitor, every ``interval_s``), over the time NetScan was running;
* **coverage %** = probes sent / probes that *would* have been sent had
  NetScan run the whole window — so "99.9 % over 3 % coverage" is not
  mistaken for a month of perfect uptime;
* **outage** = a confirmed down transition (``down_after`` failed ticks)
  until the next up transition; **MTTR** = mean outage duration.
"""

from __future__ import annotations

import ipaddress
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from netscan.classify import classify, mac_info
from netscan.security import assess, level_for

WINDOWS_H = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}


def _ports(record) -> list[dict[str, Any]]:
    try:
        data = json.loads(record.open_ports_json or "[]")
        return [p for p in data if isinstance(p, dict)]
    except (ValueError, TypeError):
        return []


def _bucket_rows(store, live, since: datetime, mac: str | None = None) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for b in store.uptime_buckets(since=since, mac=mac):
        rows[b.device_mac].append(
            {
                "start": b.bucket_start,
                "probes": b.probes,
                "up": b.up,
                "rtt_sum": b.rtt_sum_ms,
                "rtt_n": b.rtt_count,
                "rtt_min": b.rtt_min_ms,
                "rtt_max": b.rtt_max_ms,
            }
        )
    if live is not None:
        for p in live.pending_rows():
            if (mac and p["mac"] != mac) or p["bucket_start"] < since:
                continue
            rows[str(p["mac"])].append(
                {
                    "start": p["bucket_start"],
                    "probes": p["probes"],
                    "up": p["up"],
                    "rtt_sum": p["rtt_sum_ms"],
                    "rtt_n": p["rtt_count"],
                    "rtt_min": p["rtt_min_ms"],
                    "rtt_max": p["rtt_max_ms"],
                }
            )
    return rows


def _outages(events, now: datetime) -> list[dict[str, Any]]:
    """Pair down→up transitions (events newest-first in, oldest-first out)."""
    outages: list[dict[str, Any]] = []
    open_down: datetime | None = None
    for ev in sorted(events, key=lambda e: e.created_at):
        if ev.kind == "down" and open_down is None:
            open_down = ev.created_at
        elif ev.kind == "up" and open_down is not None:
            outages.append(
                {
                    "start": open_down.isoformat(timespec="seconds"),
                    "end": ev.created_at.isoformat(timespec="seconds"),
                    "duration_s": round((ev.created_at - open_down).total_seconds()),
                    "ongoing": False,
                }
            )
            open_down = None
    if open_down is not None:
        outages.append(
            {
                "start": open_down.isoformat(timespec="seconds"),
                "end": None,
                "duration_s": round((now - open_down).total_seconds()),
                "ongoing": True,
            }
        )
    return outages


def uptime_report(
    store,
    live,
    *,
    hours: float = 24,
    slots: int = 48,
    mac: str | None = None,
    interval_s: float = 5.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Availability per device: windows, timeline slots, outages, MTTR."""
    now = now or datetime.now()
    hours = max(1.0, min(float(hours), 720.0))
    slots = max(6, min(int(slots), 288))
    longest = max(hours, 720.0)
    rows = _bucket_rows(store, live, now - timedelta(hours=longest), mac)
    events = store.device_events(mac=mac, since=now - timedelta(days=30), kinds={"up", "down"}, limit=5000)
    events_by_mac: dict[str, list] = defaultdict(list)
    for ev in events:
        events_by_mac[ev.device_mac].append(ev)
    live_by_mac = {d["mac"]: d for d in (live.snapshot()["devices"] if live is not None else [])}

    slot_s = hours * 3600 / slots
    window_start = now - timedelta(hours=hours)
    devices_out = []
    for record in store.list_devices():
        if mac and record.mac != mac:
            continue
        drows = rows.get(record.mac, [])
        windows: dict[str, dict[str, float | None]] = {}
        for label, h in WINDOWS_H.items():
            since = now - timedelta(hours=h)
            sel = [r for r in drows if r["start"] >= since - timedelta(seconds=300)]
            probes = sum(r["probes"] for r in sel)
            up = sum(r["up"] for r in sel)
            expected = h * 3600 / interval_s
            windows[label] = {
                "availability_pct": round(100 * up / probes, 3) if probes else None,
                "coverage_pct": round(min(100.0, 100 * probes / expected), 1) if expected else None,
                "probes": probes,
            }
        timeline = []
        for i in range(slots):
            s_start = window_start + timedelta(seconds=i * slot_s)
            s_end = s_start + timedelta(seconds=slot_s)
            sel = [r for r in drows if s_start <= r["start"] < s_end]
            probes = sum(r["probes"] for r in sel)
            up = sum(r["up"] for r in sel)
            rtt_n = sum(r["rtt_n"] for r in sel)
            mins = [r["rtt_min"] for r in sel if r["rtt_min"] is not None]
            maxs = [r["rtt_max"] for r in sel if r["rtt_max"] is not None]
            timeline.append(
                {
                    "start": s_start.isoformat(timespec="seconds"),
                    "availability_pct": round(100 * up / probes, 2) if probes else None,
                    "probes": probes,
                    "rtt_avg_ms": round(sum(r["rtt_sum"] for r in sel) / rtt_n, 3) if rtt_n else None,
                    "rtt_min_ms": round(min(mins), 3) if mins else None,
                    "rtt_max_ms": round(max(maxs), 3) if maxs else None,
                }
            )
        outages = _outages(events_by_mac.get(record.mac, []), now)
        closed = [o for o in outages if not o["ongoing"]]
        recent = [o for o in outages if datetime.fromisoformat(o["start"]) >= now - timedelta(hours=24)]
        live_row = live_by_mac.get(record.mac, {})
        devices_out.append(
            {
                "mac": record.mac,
                "ip": record.ip,
                "name": record.hostname or record.mdns_name or record.ip,
                "vendor": record.vendor,
                "trusted": record.trusted,
                "online": bool(live_row.get("up", record.online)),
                "state_since": live_row.get("since"),
                "state_since_exact": bool(live_row.get("since_exact")),
                "method": live_row.get("method", ""),
                "latency_ms": live_row.get("latency_ms", record.last_latency_ms),
                "last_seen": record.last_seen.isoformat(timespec="seconds"),
                "windows": windows,
                "timeline": timeline,
                "outages": outages[-50:],
                "outages_24h": len(recent),
                "outages_30d": len(outages),
                "longest_outage_s": max((o["duration_s"] for o in outages), default=None),
                "mttr_s": round(sum(o["duration_s"] for o in closed) / len(closed)) if closed else None,
            }
        )
    devices_out.sort(
        key=lambda d: (
            d["windows"]["24h"]["availability_pct"] is None,
            d["windows"]["24h"]["availability_pct"]
            if d["windows"]["24h"]["availability_pct"] is not None
            else 0,
        )
    )
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "hours": hours,
        "slots": slots,
        "slot_s": round(slot_s),
        "interval_s": interval_s,
        "definitions": {
            "availability_pct": "probes answered / probes sent while NetScan was running",
            "coverage_pct": "probes sent / probes expected for the whole window",
            "outage": "confirmed down transition until the next up transition",
            "mttr_s": "mean duration of the closed outages in the last 30 days, seconds",
        },
        "devices": devices_out,
    }


def _latest_scan_devices(latest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not latest:
        return {}
    return {d.get("ip", ""): d for d in latest.get("devices", []) if isinstance(d, dict)}


def device_view(
    record, scan_dev: dict[str, Any] | None, gateway_ip: str | None, local_ip: str | None
) -> dict[str, Any]:
    ports = _ports(record)
    c = classify(
        ip=record.ip,
        mac=record.mac,
        vendor=record.vendor,
        hostname=record.hostname,
        mdns_name=record.mdns_name,
        mdns_services=(scan_dev or {}).get("mdns_services", []),
        ports={int(p["port"]) for p in ports if p.get("port")},
        os_guess=record.os_guess,
        web_titles=[h.get("title", "") for h in (scan_dev or {}).get("http", []) or []],
        gateway_ip=gateway_ip,
        local_ip=local_ip,
    )
    return {"classification": c.as_dict(), "mac_info": mac_info(record.mac).as_dict(), "ports": ports}


def network_map(
    store, latest: dict[str, Any] | None, live, gateway_ip: str | None, local_ip: str | None
) -> dict[str, Any]:
    """Nodes (gateway at the centre) with role, state, RTT and risk."""
    scan_devs = _latest_scan_devices(latest)
    live_by_mac = {d["mac"]: d for d in (live.snapshot()["devices"] if live is not None else [])}
    findings_by_ip: dict[str, list] = defaultdict(list)
    for f in (latest or {}).get("vulnerabilities", []):
        host = re.sub(r"^https?://", "", f.get("matched_at", "")).split("/")[0].split(":")[0]
        findings_by_ip[host].append(f)

    nodes = []
    for record in store.list_devices():
        scan_dev = scan_devs.get(record.ip)
        view = device_view(record, scan_dev, gateway_ip, local_ip)
        risk = assess(
            {**record.model_dump(), "ports": view["ports"]},
            scan_dev,
            findings_by_ip.get(record.ip),
            conflict_macs=(scan_dev or {}).get("conflict_macs") or None,
        )
        lrow = live_by_mac.get(record.mac, {})
        nodes.append(
            {
                "id": record.mac,
                "mac": record.mac,
                "ip": record.ip,
                "name": record.hostname or record.mdns_name or record.ip,
                "vendor": record.vendor,
                "role": view["classification"]["role"],
                "role_reasons": view["classification"]["reasons"],
                "online": bool(lrow.get("up", record.online)),
                "method": lrow.get("method", ""),
                "latency_ms": lrow.get("latency_ms") if lrow else record.last_latency_ms,
                "ports": [p["port"] for p in view["ports"]],
                "web": len((scan_dev or {}).get("http", []) or []),
                "trusted": record.trusted,
                "risk_score": risk["score"],
                "risk_level": risk["level"],
                "randomized_mac": view["mac_info"]["randomized"],
                "virtual": view["mac_info"]["virtual_platform"],
            }
        )
    ips = {n["ip"] for n in nodes}
    for synthetic_ip, role, name in (
        (gateway_ip, "gateway", "gateway"),
        (local_ip, "netscan", "NetScan host"),
    ):
        if synthetic_ip and synthetic_ip not in ips:
            nodes.append(
                {
                    "id": f"synthetic:{synthetic_ip}",
                    "mac": "",
                    "ip": synthetic_ip,
                    "name": name,
                    "vendor": "",
                    "role": role,
                    "role_reasons": ["not in the inventory (no MAC seen)"],
                    "online": True,
                    "method": "",
                    "latency_ms": None,
                    "ports": [],
                    "web": 0,
                    "trusted": True,
                    "risk_score": 0,
                    "risk_level": "low",
                    "randomized_mac": False,
                    "virtual": "",
                }
            )
    centre = next((n for n in nodes if n["role"] == "gateway"), None)
    edges = [
        {"source": centre["id"], "target": n["id"], "latency_ms": n["latency_ms"]}
        for n in nodes
        if centre is not None and n is not centre
    ]
    return {
        "network": (latest or {}).get("network", ""),
        "gateway_ip": gateway_ip,
        "local_ip": local_ip,
        "nodes": nodes,
        "edges": edges,
        "roles": dict(Counter(n["role"] for n in nodes)),
    }


def ip_map(network: str, store, gateway_ip: str | None, local_ip: str | None, live=None) -> dict[str, Any]:
    """Every address of the subnet with its state (IPAM view). Max /22."""
    net = ipaddress.IPv4Network(network, strict=False)
    if net.num_addresses > 1024:
        raise ValueError(f"{net} has {net.num_addresses} addresses; the IP map supports up to a /22 (1024)")
    by_ip = {r.ip: r for r in store.list_devices()}
    live_up = {d["ip"]: d["up"] for d in (live.snapshot()["devices"] if live is not None else [])}
    cells = []
    counts: Counter[str] = Counter()
    for addr in net:
        ip = str(addr)
        record = by_ip.get(ip)
        if addr == net.network_address and net.prefixlen < 31:
            state = "network"
        elif addr == net.broadcast_address and net.prefixlen < 31:
            state = "broadcast"
        elif ip == gateway_ip:
            state = "gateway"
        elif ip == local_ip:
            state = "self"
        elif record is not None:
            state = "online" if live_up.get(ip, record.online) else "offline"
        else:
            state = "free"
        counts[state] += 1
        cells.append(
            {
                "ip": ip,
                "state": state,
                "mac": record.mac if record else "",
                "name": (record.hostname or record.mdns_name or record.vendor) if record else "",
                "last_seen": record.last_seen.isoformat(timespec="seconds") if record else None,
            }
        )
    usable = max(1, net.num_addresses - (2 if net.prefixlen < 31 else 0))
    used = usable - counts["free"]
    return {
        "network": str(net),
        "size": net.num_addresses,
        "usable": usable,
        "used": used,
        "utilization_pct": round(100 * used / usable, 1),
        "counts": dict(counts),
        "cells": cells,
    }


def security_report(
    store, latest: dict[str, Any] | None, gateway_ip: str | None, local_ip: str | None
) -> dict[str, Any]:
    """Per-device risk ranking + network-wide findings."""
    scan_devs = _latest_scan_devices(latest)
    vulns = (latest or {}).get("vulnerabilities", [])
    findings_by_ip: dict[str, list] = defaultdict(list)
    for f in vulns:
        host = re.sub(r"^https?://", "", f.get("matched_at", "")).split("/")[0].split(":")[0]
        findings_by_ip[host].append(f)

    devices = []
    exposure: Counter[str] = Counter()
    certs = []
    randomized = 0
    for record in store.list_devices():
        scan_dev = scan_devs.get(record.ip)
        view = device_view(record, scan_dev, gateway_ip, local_ip)
        risk = assess(
            {**record.model_dump(), "ports": view["ports"]},
            scan_dev,
            findings_by_ip.get(record.ip),
            conflict_macs=(scan_dev or {}).get("conflict_macs") or None,
        )
        for factor in risk["factors"]:
            if factor["id"].startswith("port-"):
                exposure[factor["id"][5:]] += 1
        if view["mac_info"]["randomized"]:
            randomized += 1
        for http in (scan_dev or {}).get("http", []) or []:
            tls = http.get("tls")
            if tls:
                certs.append(
                    {
                        "url": http.get("url"),
                        "ip": record.ip,
                        "subject": tls.get("subject", ""),
                        "issuer": tls.get("issuer", ""),
                        "not_after": tls.get("not_after", ""),
                        "days_remaining": tls.get("days_remaining"),
                        "self_signed": tls.get("self_signed", False),
                        "version": tls.get("version", ""),
                    }
                )
        devices.append(
            {
                "mac": record.mac,
                "ip": record.ip,
                "name": record.hostname or record.mdns_name or record.ip,
                "vendor": record.vendor,
                "role": view["classification"]["role"],
                "trusted": record.trusted,
                "online": record.online,
                **risk,
            }
        )
    devices.sort(key=lambda d: -d["score"])
    certs.sort(key=lambda c: (c["days_remaining"] is None, c["days_remaining"] or 0))
    gateway_history = []
    if gateway_ip:
        gateway_history = [
            {"at": ev.created_at.isoformat(timespec="seconds"), "detail": ev.detail}
            for ev in store.device_events(kinds={"gateway_mac_changed"}, limit=20)
        ]
    conflicts = [
        {"ip": d.get("ip"), "macs": [d.get("mac"), *d.get("conflict_macs", [])]}
        for d in scan_devs.values()
        if d.get("conflict_macs")
    ]
    levels = Counter(d["level"] for d in devices)
    avg = round(sum(d["score"] for d in devices) / len(devices), 1) if devices else None
    return {
        "summary": {
            "devices": len(devices),
            "by_level": {lvl: levels.get(lvl, 0) for lvl in ("critical", "high", "medium", "low")},
            "avg_score": avg,
            "network_level": level_for(round(avg)) if avg is not None else None,
            "untrusted": sum(1 for d in devices if not d["trusted"]),
            "randomized_macs": randomized,
            "findings": len(vulns),
            "certificates": len(certs),
            "certs_expiring_30d": sum(
                1 for c in certs if c["days_remaining"] is not None and c["days_remaining"] < 30
            ),
        },
        "devices": devices,
        "exposure": [{"port": int(p), "devices": n} for p, n in exposure.most_common()],
        "certificates": certs,
        "findings": vulns,
        "conflicts": conflicts,
        "gateway": {
            "ip": gateway_ip,
            "mac": (latest or {}).get("gateway_mac", ""),
            "history": gateway_history,
        },
        "scale": "0-19 low · 20-44 medium · 45-69 high · 70-100 critical (additive factors, capped at 100)",
    }


# --------------------------------------------------------------------------- #
# Prometheus text exposition (format 0.0.4)
# --------------------------------------------------------------------------- #
def _label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def prometheus(state, uptime: dict[str, Any] | None) -> str:
    lines: list[str] = []

    def metric(
        name: str, kind: str, help_text: str, samples: list[tuple[dict[str, object], float | int | None]]
    ) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {kind}")
        for labels, value in samples:
            if value is None:
                continue
            label_str = ",".join(f'{k}="{_label(v)}"' for k, v in labels.items())
            lines.append(f"{name}{{{label_str}}} {value}" if label_str else f"{name} {value}")

    devices = state.store.list_devices()
    snap = state.live.snapshot() if state.live is not None else {"devices": [], "series": []}
    live_by_mac = {d["mac"]: d for d in snap["devices"]}

    def labels(d) -> dict[str, object]:
        return {"mac": d.mac, "ip": d.ip, "name": d.hostname or d.mdns_name or d.ip}

    metric("netscan_devices", "gauge", "Devices in the inventory", [({}, len(devices))])
    metric(
        "netscan_devices_online",
        "gauge",
        "Devices currently online",
        [({}, sum(1 for d in devices if d.online))],
    )
    metric(
        "netscan_device_up",
        "gauge",
        "1 if the device is up (live monitor state with hysteresis), else 0",
        [(labels(d), 1 if live_by_mac.get(d.mac, {}).get("up", d.online) else 0) for d in devices],
    )
    metric(
        "netscan_device_rtt_seconds",
        "gauge",
        "Last live-probe round-trip time in seconds",
        [
            (labels(d), round(live_by_mac[d.mac]["latency_ms"] / 1000, 6))
            for d in devices
            if live_by_mac.get(d.mac, {}).get("latency_ms") is not None
        ],
    )
    if uptime:
        for window in ("24h", "7d", "30d"):
            metric(
                "netscan_device_availability_ratio",
                "gauge",
                "Probes answered / probes sent over the window (0-1)",
                [
                    (
                        {"mac": d["mac"], "ip": d["ip"], "name": d["name"], "window": window},
                        round(d["windows"][window]["availability_pct"] / 100, 5)
                        if d["windows"][window]["availability_pct"] is not None
                        else None,
                    )
                    for d in uptime["devices"]
                ],
            )
    metric(
        "netscan_alerts_unacknowledged",
        "gauge",
        "Alerts not yet acknowledged",
        [({}, len(state.store.list_alerts(unacknowledged_only=True)))],
    )
    metric(
        "netscan_scans_completed_total",
        "counter",
        "Scans completed since start",
        [({}, state.scans_completed)],
    )
    metric(
        "netscan_last_scan_duration_seconds",
        "gauge",
        "Duration of the last scan in seconds",
        [({}, state.last_scan_duration_s)],
    )
    last = snap["series"][-1] if snap["series"] else {}
    metric(
        "netscan_gateway_rtt_seconds",
        "gauge",
        "Gateway ICMP RTT in seconds (live monitor)",
        [({}, round(last["gateway_ms"] / 1000, 6) if last.get("gateway_ms") is not None else None)],
    )
    metric(
        "netscan_wan_rtt_seconds",
        "gauge",
        "Mean ICMP RTT to the WAN targets in seconds",
        [({}, round(last["wan_ms"] / 1000, 6) if last.get("wan_ms") is not None else None)],
    )
    return "\n".join(lines) + "\n"
