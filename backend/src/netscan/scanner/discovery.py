"""Network discovery: local network detection, ARP scanning and the
unprivileged fallback sweep.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import ipaddress
import platform
import re
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from netscan.events import emit, fmt_s
from netscan.scanner import icmp

try:
    import netifaces
except ImportError:  # optional dependency
    netifaces = None

# The fallback sweep pings every address; past a /20 (4094 hosts) it would
# take minutes, so larger ranges need the real ARP scan (admin/root).
SWEEP_MAX_HOSTS = 4096


class ScanPrereqError(RuntimeError):
    """Raised when the machine cannot run an ARP scan (privileges/Npcap)."""


def is_elevated() -> bool:
    """True when running with the privileges raw packet capture needs."""
    if platform.system() == "Windows":
        import ctypes

        windll = getattr(ctypes, "windll", None)  # typeshed: Windows-only
        if windll is None:
            return False
        try:
            return bool(windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    import os

    geteuid = getattr(os, "geteuid", None)  # typeshed: POSIX-only
    return geteuid is not None and geteuid() == 0


def check_prereqs() -> None:
    """Fail fast with an actionable message instead of hanging in scapy."""
    if not is_elevated():
        raise ScanPrereqError(
            "The ARP scan needs administrator privileges. "
            "On Windows start the server with netscan.bat serve (it elevates itself) "
            "or from an Administrator terminal; on Linux use sudo."
        )
    if platform.system() == "Windows":
        # scapy needs the Npcap driver; without it srp() can block forever
        try:
            out = subprocess.run(
                ["sc", "query", "npcap"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if "RUNNING" not in out.stdout:
                raise ScanPrereqError(
                    "Npcap is not installed or its driver is not running. "
                    "Install Npcap (https://npcap.com) or run: sc start npcap"
                )
        except FileNotFoundError:
            pass  # 'sc' missing is not a blocker by itself


def normalize_mac(mac: str) -> str:
    """'A-B-C-D-E-F' / 'aa:bb:..' / 'a:b:c:d:e:f' → 'aa:bb:cc:dd:ee:ff'."""
    parts = re.split(r"[:\-.]", mac.strip().lower())
    if len(parts) == 3 and all(len(p) == 4 for p in parts):  # Cisco aabb.ccdd.eeff
        parts = [p[i : i + 2] for p in parts for i in (0, 2)]
    if len(parts) != 6:
        return mac.strip().lower()
    return ":".join(p.zfill(2) for p in parts)


def _iface_network(iface: str) -> tuple[str, str, str] | None:
    """(network_cidr, ip, iface) for a given interface, or None if unusable."""
    if netifaces is None:
        return None
    addrs = netifaces.ifaddresses(iface)
    if netifaces.AF_INET not in addrs:
        return None
    for addr in addrs[netifaces.AF_INET]:
        ip = addr.get("addr", "")
        netmask = addr.get("netmask", "")
        if ip and netmask and not ip.startswith("127."):
            try:
                network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
                return str(network), ip, str(iface)
            except ValueError:
                continue
    return None


def _primary_ip() -> str:
    """Source IP the OS would use for off-link traffic (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return str(s.getsockname()[0])
    finally:
        s.close()


def _psutil_network(ip: str) -> tuple[str, str, str] | None:
    """Exact CIDR + interface name for ``ip`` from psutil's netmask."""
    try:
        import psutil
    except ImportError:
        return None
    for name, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET and addr.address == ip and addr.netmask:
                try:
                    net = ipaddress.IPv4Network(f"{ip}/{addr.netmask}", strict=False)
                except ValueError:
                    continue
                return str(net), ip, name
    return None


def local_mac(ip: str) -> str:
    """MAC of the local adapter that owns ``ip`` ('' if unknown).

    A host never answers its own ARP request nor caches itself, so neither
    discovery method can see the machine NetScan runs on; without this it
    was missing from the inventory (devices without MAC are not stored).
    """
    try:
        import psutil
    except ImportError:
        return ""
    link = getattr(psutil, "AF_LINK", None)
    for addrs in psutil.net_if_addrs().values():
        if any(a.family == socket.AF_INET and a.address == ip for a in addrs):
            for a in addrs:
                if a.family == link and a.address:
                    mac = normalize_mac(a.address)
                    if len(mac) == 17 and _usable_mac(mac):
                        return mac
    return ""


def get_local_network() -> tuple[str, str, str]:
    """Return (network_cidr, local_ip, interface_name).

    Prefers the interface that owns the default gateway — iterating all
    interfaces picks up VPN/virtual adapters (WSL, Hyper-V, Docker) first
    on many Windows machines.
    """
    if netifaces:
        gateways = netifaces.gateways()
        default = gateways.get("default", {})
        gw = default.get(netifaces.AF_INET)
        if gw and len(gw) > 1:
            primary = _iface_network(str(gw[1]))
            if primary:
                return primary
    ip = _primary_ip()
    found = _psutil_network(ip)
    if found:
        return found
    if netifaces:
        for iface in netifaces.interfaces():
            found = _iface_network(iface)
            if found:
                return found
    return f"{ip.rsplit('.', 1)[0]}.0/24", ip, "default"


def default_gateway() -> str | None:
    """IPv4 default gateway, or None. No external dependency required."""
    if netifaces:
        gw = netifaces.gateways().get("default", {}).get(netifaces.AF_INET)
        if gw:
            return str(gw[0])
    system = platform.system()
    try:
        if system == "Linux":
            for line in Path("/proc/net/route").read_text().splitlines()[1:]:
                fields = line.split()
                if len(fields) > 2 and fields[1] == "00000000" and int(fields[3], 16) & 2:
                    return socket.inet_ntoa(bytes.fromhex(fields[2])[::-1])
        elif system == "Windows":
            out = subprocess.run(
                ["route", "print", "-4", "0.0.0.0"], capture_output=True, text=True, timeout=5, check=False
            ).stdout
            for line in out.splitlines():
                fields = line.split()
                if len(fields) >= 5 and fields[0] == "0.0.0.0" and fields[1] == "0.0.0.0":
                    ipaddress.IPv4Address(fields[2])
                    return fields[2]
        else:  # macOS / BSD
            out = subprocess.run(
                ["route", "-n", "get", "default"], capture_output=True, text=True, timeout=5, check=False
            ).stdout
            match = re.search(r"gateway:\s*(\S+)", out)
            if match:
                return match.group(1)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


_ARP_WIN_RE = re.compile(r"^\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5})\s+(\S+)")
_ARP_BSD_RE = re.compile(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-fA-F:]+)")


def _usable_mac(mac: str) -> bool:
    if mac in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
        return False
    return not int(mac.split(":")[0], 16) & 0x01  # multicast/broadcast bit


def parse_neighbor_output(text: str, system: str) -> dict[str, str]:
    """Parse ``arp -a`` (Windows), ``arp -an`` (BSD) or /proc/net/arp."""
    table: dict[str, str] = {}
    if system == "Linux":
        for line in text.splitlines()[1:]:
            fields = line.split()
            # IP, HW type, Flags, HW address, Mask, Device — flags 0x2 = complete
            if len(fields) >= 4 and int(fields[2], 16) & 0x2:
                mac = normalize_mac(fields[3])
                if _usable_mac(mac):
                    table[fields[0]] = mac
        return table
    pattern = _ARP_WIN_RE if system == "Windows" else _ARP_BSD_RE
    for line in text.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        mac = normalize_mac(match.group(2))
        if len(mac) == 17 and _usable_mac(mac):
            table[match.group(1)] = mac
    return table


def neighbor_table() -> dict[str, str]:
    """The OS ARP/neighbour cache as {ip: mac}. Unprivileged on every OS."""
    system = platform.system()
    try:
        if system == "Linux":
            text = Path("/proc/net/arp").read_text()
        else:
            args = ["arp", "-a"] if system == "Windows" else ["arp", "-an"]
            text = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse_neighbor_output(text, system)


def _srp_with_watchdog(packet, timeout: int, iface: str | None):
    """Run scapy.srp with a hard watchdog: never hang the scan forever."""
    from scapy.all import conf, srp

    conf.verbosity = 0  # type: ignore[attr-defined]
    result: list = []
    error: list[BaseException] = []

    def _worker() -> None:
        try:
            kwargs: dict = {"timeout": timeout, "verbose": False}
            if iface and iface != "default":
                kwargs["iface"] = iface
            answered, _ = srp(packet, **kwargs)
            result.extend(answered)
        except BaseException as exc:
            error.append(exc)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout * 4 + 20)
    if thread.is_alive():
        raise ScanPrereqError(
            "The ARP scan did not answer in time. Check that the server runs "
            "as administrator and that Npcap works (sc query npcap)."
        )
    if error:
        raise ScanPrereqError(f"ARP scan failed: {error[0]}") from error[0]
    return result


def arp_scan(network_cidr: str, timeout: int = 3, iface: str | None = None) -> list[dict[str, str]]:
    """Broadcast ARP discovery. Requires elevated privileges on most OSes.

    Networks larger than a /24 are scanned one /24 chunk at a time: a single
    ARP storm over a /16 (65k hosts) saturates the NIC buffer and loses
    replies, and the watchdog would fire long before it finished.

    Two different MACs answering for the same IP (an IP conflict, or ARP
    spoofing) are reported in the device's ``conflict`` key.
    """
    check_prereqs()
    from scapy.all import ARP, Ether  # type: ignore[attr-defined]

    network = ipaddress.IPv4Network(network_cidr, strict=False)
    chunks = [network] if network.num_addresses <= 256 else list(network.subnets(new_prefix=24))
    emit(
        "discovery",
        f"ARP who-has sweep {network} · {network.num_addresses} addresses in {len(chunks)} chunk(s) · "
        f"iface {iface or 'auto'} · {timeout} s wait per chunk",
        cidr=str(network),
    )

    macs_by_ip: dict[str, list[str]] = {}
    for chunk in chunks:
        packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=str(chunk))
        answered = _srp_with_watchdog(packet, timeout, iface)
        for _, received in answered:
            mac = normalize_mac(received.hwsrc)
            seen = macs_by_ip.setdefault(received.psrc, [])
            if mac not in seen:
                seen.append(mac)

    devices: list[dict[str, str]] = []
    for ip, macs in macs_by_ip.items():
        entry = {"ip": ip, "mac": macs[0]}
        if len(macs) > 1:
            entry["conflict"] = ",".join(macs)
            emit(
                "security", f"IP conflict: {ip} answered from {len(macs)} MACs ({', '.join(macs)})", "warning"
            )
        devices.append(entry)
    devices.sort(key=lambda d: ipaddress.IPv4Address(d["ip"]))
    return devices


def sweep_scan(
    network_cidr: str,
    timeout: float = 0.8,
    workers: int = 64,
    progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, str]]:
    """Unprivileged discovery: ICMP echo to every host + the OS ARP cache.

    Even when a host's firewall drops the echo, the attempt makes the OS
    resolve its MAC by ARP, so it still shows up in the neighbour table
    read afterwards — that is what catches ping-shy Windows PCs. Hosts
    off-link (routed subnets) only appear if they answer ICMP, and then
    without a MAC.
    """
    network = ipaddress.IPv4Network(network_cidr, strict=False)
    hosts = [str(h) for h in network.hosts()]
    if len(hosts) > SWEEP_MAX_HOSTS:
        raise ScanPrereqError(
            f"{network} has {len(hosts)} hosts: too large for the unprivileged sweep "
            f"(max {SWEEP_MAX_HOSTS}). Run NetScan as administrator/root for the ARP scan."
        )
    emit(
        "discovery",
        f"ICMP sweep {network} · {len(hosts)} hosts · {workers} threads · {int(timeout * 1000)} ms timeout "
        f"· ICMP backend {icmp.backend()}",
        cidr=str(network),
    )
    start = time.perf_counter()
    alive: dict[str, float] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(icmp.echo, ip, timeout): ip for ip in hosts}
        for fut in as_completed(futures):
            done += 1
            ip = futures[fut]
            try:
                rtt = fut.result()
            except Exception:
                rtt = None
            if rtt is not None:
                alive[ip] = rtt
            if progress and (done % 16 == 0 or done == len(hosts)):
                progress(done, len(hosts))

    neighbors = {ip: mac for ip, mac in neighbor_table().items() if ipaddress.IPv4Address(ip) in network}
    found = set(alive) | set(neighbors)
    emit(
        "discovery",
        f"sweep done in {fmt_s(time.perf_counter() - start)}: {len(alive)} answered ICMP, "
        f"{len(neighbors)} in the ARP cache, {len(found)} hosts total "
        f"({len(set(neighbors) - set(alive))} only visible at L2 — ICMP filtered)",
    )
    devices = [{"ip": ip, "mac": neighbors.get(ip, "")} for ip in found]
    devices.sort(key=lambda d: ipaddress.IPv4Address(d["ip"]))
    return devices


def discover_hosts(
    network_cidr: str,
    iface: str | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[list[dict[str, str]], str]:
    """ARP scan when possible, the unprivileged sweep otherwise.

    Returns ``(devices, method)`` where method is ``"arp"`` or ``"sweep"``.
    Running without admin used to fail the whole scan with an error buried
    in netscan.log; now it degrades and says so on the event feed.
    """
    try:
        return arp_scan(network_cidr, iface=iface), "arp"
    except (ScanPrereqError, ImportError, OSError) as exc:
        emit(
            "discovery",
            f"ARP scan unavailable — {exc} Falling back to ICMP sweep + OS ARP cache "
            "(same results on the local segment, slower).",
            "warning",
        )
        return sweep_scan(network_cidr, progress=progress), "sweep"
