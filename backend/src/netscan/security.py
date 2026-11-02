"""Per-device exposure / risk assessment.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Crosses the inventory (trust, first seen, MAC), the latest scan (open ports
and service versions, web UIs and their certificates) and the findings of
nuclei/testssl.sh into one 0-100 score per device. The number is never a
black box: every point comes from a named factor with the evidence that
triggered it and what to do about it.

Scale: 0-19 low · 20-44 medium · 45-69 high · 70-100 critical.
Points are additive and capped at 100. They encode exposure on a *LAN*
(a homelab threat model), not Internet-facing severity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from netscan.classify import mac_info

# port -> (points, severity, title, remediation)
RISKY_PORTS: dict[int, tuple[int, str, str, str]] = {
    23: (30, "critical", "Telnet open — credentials travel in cleartext", "Disable Telnet; use SSH."),
    2375: (
        40,
        "critical",
        "Docker API without TLS — root on the host for anyone on the LAN",
        "Bind dockerd to a socket or enable TLS (2376).",
    ),
    6379: (
        25,
        "high",
        "Redis reachable — no authentication by default",
        "Set requirepass/ACLs and bind to localhost.",
    ),
    27017: (
        25,
        "high",
        "MongoDB reachable — often deployed without auth",
        "Enable authorization and bind to localhost.",
    ),
    9200: (20, "high", "Elasticsearch HTTP API reachable", "Enable security (xpack) or firewall it."),
    5900: (
        20,
        "high",
        "VNC exposed — frequently weak or no password",
        "Tunnel VNC over SSH or restrict by firewall.",
    ),
    21: (15, "medium", "FTP open — cleartext credentials", "Use SFTP/FTPS."),
    3389: (15, "medium", "RDP exposed on the LAN", "Require NLA, restrict to admin hosts."),
    1883: (15, "medium", "MQTT without TLS — often allows anonymous publish", "Require auth; use 8883/TLS."),
    445: (10, "medium", "SMB exposed", "Disable SMBv1, keep the host patched, restrict shares."),
    5985: (10, "medium", "WinRM over HTTP", "Use WinRM over HTTPS (5986) or disable."),
    3306: (10, "medium", "MySQL/MariaDB reachable from the LAN", "Bind to localhost or firewall it."),
    5432: (10, "medium", "PostgreSQL reachable from the LAN", "Restrict pg_hba.conf / firewall it."),
    1433: (10, "medium", "MS SQL Server reachable from the LAN", "Firewall it."),
    1521: (10, "medium", "Oracle listener reachable from the LAN", "Firewall it."),
    139: (5, "low", "NetBIOS session service", "Disable NetBIOS over TCP/IP if unused."),
    111: (5, "low", "RPC portmapper exposed", "Firewall it if NFS is not served to the LAN."),
}

_FINDING_POINTS = {"critical": 40, "high": 25, "medium": 10, "low": 3}
_WEAK_TLS = {"TLSv1", "TLSv1.0", "TLSv1.1", "SSLv3", "SSLv2"}


@dataclass
class Factor:
    id: str
    points: int
    severity: str  # low | medium | high | critical | info
    title: str
    evidence: str = ""
    remediation: str = ""


def level_for(score: int) -> str:
    if score >= 70:
        return "critical"
    if score >= 45:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def assess(
    device: dict[str, Any],
    scan_device: dict[str, Any] | None = None,
    findings: list[dict[str, str]] | None = None,
    *,
    conflict_macs: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Risk assessment of one inventory device.

    ``device`` is a DeviceRecord dump (trusted, first_seen, mac, ports...),
    ``scan_device`` the same host's entry in the latest ScanResult (for
    http/tls), ``findings`` the scan's vulnerabilities matching this host.
    """
    now = now or datetime.now()
    factors: list[Factor] = []

    if not device.get("trusted"):
        factors.append(
            Factor(
                "untrusted",
                15,
                "medium",
                "Device not verified by you",
                "trusted = false",
                "Identify it and mark it as trusted, or block it at the router.",
            )
        )
    first_seen = device.get("first_seen")
    if isinstance(first_seen, str):
        try:
            first_seen = datetime.fromisoformat(first_seen)
            if first_seen.tzinfo is not None:  # API strings carry an offset
                first_seen = first_seen.astimezone().replace(tzinfo=None)
        except ValueError:
            first_seen = None
    if isinstance(first_seen, datetime) and now - first_seen < timedelta(hours=24):
        factors.append(
            Factor(
                "new",
                10,
                "medium",
                "Joined the network in the last 24 h",
                f"first seen {first_seen.isoformat(timespec='minutes')}",
            )
        )

    ports = device.get("ports") or []
    port_numbers = {int(p.get("port", 0)) for p in ports if p.get("port")}
    versions = {int(p["port"]): p.get("version", "") for p in ports if p.get("port")}
    for port in sorted(port_numbers):
        if port in RISKY_PORTS:
            points, severity, title, fix = RISKY_PORTS[port]
            version = versions.get(port, "")
            factors.append(
                Factor(
                    f"port-{port}",
                    points,
                    severity,
                    title,
                    f"{port}/tcp open" + (f" · {version}" if version else ""),
                    fix,
                )
            )
    if len(port_numbers) > 10:
        factors.append(
            Factor(
                "surface",
                10,
                "medium",
                "Large attack surface",
                f"{len(port_numbers)} open TCP ports",
                "Close services you do not use.",
            )
        )

    for http in (scan_device or {}).get("http", []) or []:
        tls = http.get("tls")
        url = http.get("url", "")
        if tls:
            days = tls.get("days_remaining")
            if days is not None and days < 0:
                factors.append(
                    Factor(
                        f"cert-expired-{url}",
                        20,
                        "high",
                        "Expired TLS certificate",
                        f"{url} expired {-days} d ago",
                        "Renew the certificate.",
                    )
                )
            elif days is not None and days < 14:
                factors.append(
                    Factor(
                        f"cert-expiring-{url}",
                        10,
                        "medium",
                        "TLS certificate about to expire",
                        f"{url} expires in {days} d",
                        "Renew it (or automate with ACME).",
                    )
                )
            if tls.get("version") in _WEAK_TLS:
                factors.append(
                    Factor(
                        f"weak-tls-{url}",
                        15,
                        "high",
                        "Obsolete TLS protocol negotiated",
                        f"{url} → {tls.get('version')}",
                        "Disable TLS < 1.2.",
                    )
                )
            if tls.get("self_signed"):
                factors.append(
                    Factor(
                        f"self-signed-{url}",
                        3,
                        "low",
                        "Self-signed certificate",
                        f"{url} · issuer {tls.get('issuer') or '?'}",
                        "Use an internal CA or ACME so browsers can verify it.",
                    )
                )
        elif url.startswith("http://") and any(
            w in (http.get("title") or "").lower() for w in ("login", "sign in", "admin", "password")
        ):
            factors.append(
                Factor(
                    f"cleartext-login-{url}",
                    8,
                    "medium",
                    "Login page served over plain HTTP",
                    f"{url} · “{http.get('title')}”",
                    "Serve the UI over HTTPS.",
                )
            )

    for finding in findings or []:
        sev = (finding.get("severity") or "").lower()
        finding_points = _FINDING_POINTS.get(sev)
        if finding_points:
            factors.append(
                Factor(
                    f"finding-{finding.get('tool', '?')}-{finding.get('template', '')}",
                    finding_points,
                    sev,
                    f"{finding.get('tool', 'scanner')}: {finding.get('name') or finding.get('template')}",
                    finding.get("matched_at", ""),
                    "See the template reference and patch/reconfigure the service.",
                )
            )

    if conflict_macs:
        factors.append(
            Factor(
                "ip-conflict",
                30,
                "high",
                "IP conflict / possible ARP spoofing",
                f"answered from {', '.join(conflict_macs)}",
                "Find both MACs on the switch; check for static IP clashes or MITM tools.",
            )
        )

    minfo = mac_info(device.get("mac", ""))
    if minfo.locally_administered and not minfo.virtual_platform and not device.get("trusted"):
        factors.append(
            Factor(
                "random-mac",
                5,
                "low",
                "Randomized MAC — vendor cannot be identified",
                device.get("mac", ""),
                "Normal for phones (private Wi-Fi address); verify the owner and mark trusted.",
            )
        )

    score = min(100, sum(f.points for f in factors))
    factors.sort(key=lambda f: -f.points)
    return {
        "score": score,
        "level": level_for(score),
        "factors": [asdict(f) for f in factors],
    }
