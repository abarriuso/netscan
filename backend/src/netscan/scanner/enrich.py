"""Per-device enrichment: hostname, vendor, ping, ports, OS heuristics.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from netscan.events import emit, fmt_ms, fmt_s
from netscan.models import PortInfo
from netscan.scanner import icmp

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
    8006: "Proxmox",
    8080: "HTTP-Alt",
    8443: "HTTPS-Alt",
    8888: "HTTP-Proxy",
    9090: "WebUI",
    27017: "MongoDB",
}

EXTENDED_PORTS: dict[int, str] = {
    111: "RPCbind",
    161: "SNMP",
    162: "SNMP-Trap",
    389: "LDAP",
    636: "LDAPS",
    514: "Syslog",
    548: "AFP",
    554: "RTSP",
    631: "IPP",
    902: "VMware-ESXi",
    1883: "MQTT",
    2049: "NFS",
    2375: "Docker-API",
    2376: "Docker-TLS",
    5000: "Synology-DSM",
    5001: "Synology-DSM-TLS",
    5353: "mDNS",
    5355: "LLMNR",
    5985: "WinRM",
    5986: "WinRM-TLS",
    8008: "Cast",
    8009: "Cast-TLS",
    8096: "Jellyfin",
    8123: "HomeAssistant",
    8883: "MQTT-TLS",
    9000: "Portainer",
    9100: "Printer",
    9200: "Elasticsearch",
    32400: "Plex",
    49152: "UPnP",
    62078: "iOS-sync",
}

_mac_lookup = None
_mac_lookup_failed = False
# Refresh the downloaded OUI database at most this often. The library's
# update_vendors() fetches several MB from the Internet; calling it on every
# process start (as before) stalled the first scan offline and hammered the
# upstream service for no benefit — OUI assignments change slowly.
_VENDOR_DB_MAX_AGE_S = 30 * 86400


def _vendor_db_stale() -> bool:
    try:
        from mac_vendor_lookup import BaseMacLookup

        path = Path(BaseMacLookup.cache_path)
    except Exception:
        return True
    return not path.is_file() or time.time() - path.stat().st_mtime > _VENDOR_DB_MAX_AGE_S


def get_vendor(mac: str) -> str:
    """OUI vendor lookup. mac_vendor_lookup is NOT thread-safe: call from the main thread."""
    global _mac_lookup, _mac_lookup_failed
    if _mac_lookup_failed or not mac:
        return ""
    if _mac_lookup is None:
        try:
            from mac_vendor_lookup import MacLookup

            _mac_lookup = MacLookup()
            if _vendor_db_stale():
                emit("discovery", "OUI vendor database missing or older than 30 d — downloading")
                try:
                    _mac_lookup.update_vendors()
                except Exception as exc:
                    emit(
                        "discovery",
                        f"OUI database download failed ({exc}); using the bundled copy",
                        "warning",
                    )
        except Exception as exc:
            _mac_lookup_failed = True
            emit("discovery", f"OUI vendor lookup unavailable: {exc}", "warning")
            return ""
    try:
        return str(_mac_lookup.lookup(mac))
    except Exception:
        return ""


def resolve_vendors(macs: list[str]) -> dict[str, str]:
    """Resolve vendors in the main thread. Returns {mac: vendor}."""
    return {mac: get_vendor(mac) for mac in dict.fromkeys(macs)}


def resolve_hostname(ip: str) -> str:
    """Reverse DNS (PTR) lookup through the OS resolver."""
    start = time.perf_counter()
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
    except (socket.herror, socket.gaierror, OSError):
        hostname = ""
    elapsed = (time.perf_counter() - start) * 1000
    emit(
        "dns",
        f"PTR {ip} → {hostname or 'no record'} ({fmt_ms(elapsed)})",
        "debug" if not hostname else "info",
        host=ip,
        ms=round(elapsed, 2),
    )
    return hostname


def ping_host(ip: str, timeout: float = 1.0) -> float | None:
    """One ICMP echo (see scanner.icmp). Latency in ms or None."""
    rtt = icmp.echo(ip, timeout)
    emit("icmp", f"echo {ip} → {fmt_ms(rtt) if rtt is not None else 'no reply'}", "debug", host=ip, ms=rtt)
    return rtt


def scan_port(ip: str, port: int, timeout: float = 0.5) -> bool:
    return connect_time(ip, port, timeout) is not None


def connect_time(ip: str, port: int, timeout: float = 0.5) -> float | None:
    """TCP connect() to ip:port; handshake time in ms if open, else None."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            start = time.perf_counter()
            if sock.connect_ex((ip, port)) != 0:
                return None
            return round((time.perf_counter() - start) * 1000, 2)
    except OSError:
        return None


def scan_ports(ip: str, ports: dict[int, str], max_workers: int = 50, timeout: float = 0.5) -> list[PortInfo]:
    """Threaded TCP connect() scan. Emits one event per open port."""
    open_ports: list[PortInfo] = []
    start = time.perf_counter()
    emit(
        "ports",
        f"TCP connect scan {ip} · {len(ports)} ports · {max_workers} threads · {int(timeout * 1000)} ms timeout",
        "debug",
        host=ip,
        ports=len(ports),
    )
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(ports) or 1))) as executor:
        futures = {executor.submit(connect_time, ip, port, timeout): port for port in ports}
        for future in as_completed(futures):
            port = futures[future]
            handshake = future.result()
            if handshake is not None:
                service = ports.get(port, "unknown")
                open_ports.append(PortInfo(port=port, service=service))
                emit(
                    "ports",
                    f"{ip}:{port}/tcp open · {service} · handshake {fmt_ms(handshake)}",
                    host=ip,
                    port=port,
                    service=service,
                    ms=handshake,
                )
    open_ports.sort(key=lambda p: p.port)
    emit(
        "ports",
        f"{ip}: {len(open_ports)}/{len(ports)} TCP ports open in {fmt_s(time.perf_counter() - start)}"
        + (f" → {', '.join(str(p.port) for p in open_ports)}" if open_ports else ""),
        host=ip,
        open=[p.port for p in open_ports],
    )
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
