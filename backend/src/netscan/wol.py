"""Wake-on-LAN.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import re
import socket

_MAC_RE = re.compile(r"^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$")


def wake(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    """Send a WoL magic packet for ``mac`` (any common separator)."""
    cleaned = mac.replace("-", ":").lower()
    if not _MAC_RE.match(cleaned):
        raise ValueError(f"MAC inválida: {mac}")
    mac_bytes = bytes.fromhex(cleaned.replace(":", ""))
    packet = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))
