"""Network discovery: local network detection and ARP scanning.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import ipaddress
import platform
import socket
import threading

try:
    import netifaces
except ImportError:  # optional dependency
    netifaces = None


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
            "El escaneo ARP necesita privilegios de administrador. "
            "En Windows lanza el servidor con netscan.bat serve (se auto-eleva) "
            "o desde un terminal de Administrador; en Linux usa sudo."
        )
    if platform.system() == "Windows":
        # scapy needs the Npcap driver; without it srp() can block forever
        import subprocess

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
                    "Npcap está instalado pero el driver no está en ejecución. "
                    "Reinicia el equipo o ejecuta: sc start npcap"
                )
        except FileNotFoundError:
            pass  # 'sc' missing is not a blocker by itself


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
        for iface in netifaces.interfaces():
            found = _iface_network(iface)
            if found:
                return found
    # Fallback: derive from the default route
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return f"{ip.rsplit('.', 1)[0]}.0/24", ip, "default"


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
            "El escaneo ARP no respondió a tiempo. Comprueba que el servidor "
            "corre como administrador y que Npcap funciona (sc query npcap)."
        )
    if error:
        raise ScanPrereqError(f"Fallo en el escaneo ARP: {error[0]}") from error[0]
    return result


def arp_scan(network_cidr: str, timeout: int = 3, iface: str | None = None) -> list[dict[str, str]]:
    """Broadcast ARP discovery. Requires elevated privileges on most OSes.

    Networks larger than a /24 are scanned one /24 chunk at a time: a single
    ARP storm over a /16 (65k hosts) saturates the NIC buffer and loses
    replies, and the watchdog would fire long before it finished.
    """
    check_prereqs()
    from scapy.all import ARP, Ether  # type: ignore[attr-defined]

    network = ipaddress.IPv4Network(network_cidr, strict=False)
    chunks = [network] if network.num_addresses <= 256 else list(network.subnets(new_prefix=24))

    found: dict[str, dict[str, str]] = {}
    for chunk in chunks:
        packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=str(chunk))
        answered = _srp_with_watchdog(packet, timeout, iface)
        for _, received in answered:
            found[received.psrc] = {"ip": received.psrc, "mac": received.hwsrc.lower()}

    devices = list(found.values())
    devices.sort(key=lambda d: ipaddress.IPv4Address(d["ip"]))
    return devices
