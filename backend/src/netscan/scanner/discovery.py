"""Network discovery: local network detection and ARP scanning.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import ipaddress
import socket

try:
    import netifaces  # type: ignore[import-not-found]
except ImportError:  # optional dependency
    netifaces = None  # type: ignore[assignment]


def get_local_network() -> tuple[str, str, str]:
    """Return (network_cidr, local_ip, interface_name)."""
    if netifaces:
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get("addr", "")
                    netmask = addr.get("netmask", "")
                    if ip and netmask and not ip.startswith("127."):
                        try:
                            network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
                            return str(network), ip, str(iface)
                        except ValueError:
                            continue
    # Fallback: derive from the default route
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return f"{ip.rsplit('.', 1)[0]}.0/24", ip, "default"


def arp_scan(network_cidr: str, timeout: int = 3) -> list[dict[str, str]]:
    """Broadcast ARP discovery. Requires elevated privileges on most OSes."""
    from scapy.all import ARP, Ether, conf, srp  # lazy: heavy, platform-specific init

    conf.verbosity = 0
    network = ipaddress.IPv4Network(network_cidr, strict=False)
    if network.num_addresses > 65536:
        network = ipaddress.IPv4Network(f"{network.network_address}/16", strict=False)

    packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=str(network))
    answered, _ = srp(packet, timeout=timeout, verbose=False)

    devices = [{"ip": received.psrc, "mac": received.hwsrc.lower()} for _, received in answered]
    devices.sort(key=lambda d: ipaddress.IPv4Address(d["ip"]))
    return devices
