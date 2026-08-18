"""Wake-on-LAN.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import ipaddress
import re
import socket
import time

_MAC_RE = re.compile(r"^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$")


def _default_broadcast() -> str:
    """Directed broadcast of the local network (255.255.255.255 is dropped by many routers/NICs)."""
    try:
        from netscan.scanner.discovery import get_local_network

        cidr, _, _ = get_local_network()
        return str(ipaddress.IPv4Network(cidr, strict=False).broadcast_address)
    except Exception:
        return "255.255.255.255"


def wake(mac: str, broadcast: str = "", port: int = 9, repeats: int = 3) -> None:
    """Send a WoL magic packet for ``mac`` (any common separator).

    The packet is sent ``repeats`` times: a single UDP datagram is easy to
    lose on a congested or power-saving LAN.
    """
    cleaned = mac.replace("-", ":").lower()
    if not _MAC_RE.match(cleaned):
        raise ValueError(f"MAC inválida: {mac}")
    target = broadcast or _default_broadcast()
    mac_bytes = bytes.fromhex(cleaned.replace(":", ""))
    packet = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for i in range(max(1, repeats)):
            sock.sendto(packet, (target, port))
            if i < repeats - 1:
                time.sleep(0.1)
