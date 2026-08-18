"""mDNS / Bonjour discovery via python-zeroconf (LGPL-2.1, compatible import).

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Discovers and names IoT devices (Chromecast, printers, TVs, HomeKit...) that
do not answer reverse DNS — the classic "Desconocido" entries of an ARP scan.
"""

from __future__ import annotations

import ipaddress
from collections import defaultdict

SERVICE_TYPES = [
    "_googlecast._tcp.local.",
    "_airplay._tcp.local.",
    "_raop._tcp.local.",
    "_ipp._tcp.local.",
    "_ipps._tcp.local.",
    "_printer._tcp.local.",
    "_pdl-datastream._tcp.local.",
    "_http._tcp.local.",
    "_hap._tcp.local.",
    "_homekit._tcp.local.",
    "_spotify-connect._tcp.local.",
    "_smb._tcp.local.",
    "_ssh._tcp.local.",
    "_mqtt._tcp.local.",
    "_esphomelib._tcp.local.",
    "_nvstream_dbd._tcp.local.",
]


def mdns_discover(timeout: float = 3.0) -> dict[str, dict[str, object]]:
    """Browse mDNS for ``timeout`` seconds.

    Returns ``{ip: {"name": str, "services": [str, ...]}}``.
    Empty dict if zeroconf is not installed.
    """
    try:
        from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf
    except ImportError:
        return {}

    found: dict[str, dict[str, object]] = defaultdict(lambda: {"name": "", "services": []})

    def on_service_change(
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        info = zeroconf.get_service_info(service_type, name, timeout=2000)
        if not info:
            return
        short = service_type.split(".")[0].lstrip("_")
        for raw_addr in info.addresses:
            try:
                ip = str(ipaddress.IPv4Address(raw_addr))
            except (ipaddress.AddressValueError, ValueError):
                continue
            entry = found[ip]
            if not entry["name"]:
                entry["name"] = info.server.rstrip(".") if info.server else name
            services = entry["services"]
            assert isinstance(services, list)
            if short not in services:
                services.append(short)

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, SERVICE_TYPES, handlers=[on_service_change])
        import time

        time.sleep(timeout)
    finally:
        zc.close()
    return dict(found)
