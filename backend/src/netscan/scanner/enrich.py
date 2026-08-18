"""Per-device enrichment: hostname, vendor, ping, ports, OS heuristics.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import contextlib
import platform
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from netscan.models import PortInfo

COMMON_PORTS: dict[int, str] = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    135: "RPC",
    139: "NetBIOS",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    993: "IMAPS",
    995: "POP3S",
    1433: "MSSQL",
    1521: "Oracle",
    3306: "MySQL",
    3389: "RDP",
    5432: "PostgreSQL",
    5900: "VNC",
    6379: "Redis",
    8080: "HTTP-Alt",
    8443: "HTTPS-Alt",
    8888: "HTTP-Proxy",
    9090: "WebUI",
    27017: "MongoDB",
}

EXTENDED_PORTS: dict[int, str] = {
    161: "SNMP",
    162: "SNMP-Trap",
    389: "LDAP",
    636: "LDAPS",
    514: "Syslog",
    548: "AFP",
    1883: "MQTT",
    5353: "mDNS",
    5355: "LLMNR",
    9100: "Printer",
    631: "IPP",
    8006: "Proxmox",
    49152: "UPnP",
    32400: "Plex",
    8096: "Jellyfin",
    9000: "Portainer",
}

_mac_lookup = None
_mac_lookup_failed = False


def get_vendor(mac: str) -> str:
    """OUI vendor lookup. mac_vendor_lookup is NOT thread-safe: call from the main thread."""
    global _mac_lookup, _mac_lookup_failed
    if _mac_lookup_failed:
        return ""
    if _mac_lookup is None:
        try:
            from mac_vendor_lookup import MacLookup

            _mac_lookup = MacLookup()
            with contextlib.suppress(Exception):
                _mac_lookup.update_vendors()
        except Exception:
            _mac_lookup_failed = True
            return ""
    try:
        return str(_mac_lookup.lookup(mac))
    except Exception:
        return ""


def resolve_vendors(macs: list[str]) -> dict[str, str]:
    """Resolve vendors in the main thread. Returns {mac: vendor}."""
    return {mac: get_vendor(mac) for mac in dict.fromkeys(macs)}


def resolve_hostname(ip: str) -> str:
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, OSError):
        return ""


# Matches "time=12ms", "time<1ms", "tiempo=12ms" (es), "Zeit=12ms" (de), ...
_PING_TIME_RE = re.compile(r"(?:time|tiempo|zeit|temps|tempo)\s*[=<]\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE)


def ping_host(ip: str, timeout: float = 1.0) -> float | None:
    """ICMP ping via the system binary. Returns latency in ms or None.

    Parses the latency from ping's stdout (locale-tolerant) instead of
    measuring the wall-clock of the whole subprocess, which mostly measures
    process spawn time (~30-80 ms on Windows) and hides the real RTT.
    """
    is_windows = platform.system().lower() == "windows"
    param = "-n" if is_windows else "-c"
    timeout_param = "-w" if is_windows else "-W"
    timeout_val = str(int(timeout * 1000)) if is_windows else str(int(timeout))

    try:
        start = time.perf_counter()
        result = subprocess.run(
            ["ping", param, "1", timeout_param, timeout_val, ip],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
            check=False,
        )
        elapsed = (time.perf_counter() - start) * 1000
        if result.returncode != 0:
            return None
        match = _PING_TIME_RE.search(result.stdout)
        if match:
            return round(float(match.group(1).replace(",", ".")), 1)
        # Output format not recognized: fall back to process wall-clock.
        return round(elapsed, 1)
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def scan_port(ip: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((ip, port)) == 0
    except OSError:
        return False


def scan_ports(ip: str, ports: dict[int, str], max_workers: int = 50, timeout: float = 0.5) -> list[PortInfo]:
    open_ports: list[PortInfo] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_port, ip, port, timeout): port for port in ports}
        for future in as_completed(futures):
            port = futures[future]
            if future.result():
                open_ports.append(PortInfo(port=port, service=ports.get(port, "unknown")))
    open_ports.sort(key=lambda p: p.port)
    return open_ports


def detect_os_from_ports(open_ports: list[PortInfo]) -> str:
    """Heuristic OS guess from open ports (fallback when nmap -O is unavailable)."""
    port_set = {p.port for p in open_ports}
    if port_set & {3389, 135} or (445 in port_set and 22 not in port_set):
        return "Windows"
    if 548 in port_set or 62078 in port_set:
        return "Apple"
    if 22 in port_set:
        return "Linux/Unix"
    return ""
