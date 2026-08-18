"""Notification delivery via Apprise (ntfy, Telegram, Discord, +80 services).

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

from netscan.db.models import AlertRecord

_TITLES = {
    "new_device": "NetScan — nuevo dispositivo",
    "mac_changed": "NetScan — IP/MAC cambiada",
    "device_down": "NetScan — dispositivo caído",
    "device_back": "NetScan — dispositivo de vuelta",
}


def send_alerts(alerts: list[AlertRecord], urls: list[str]) -> int:
    """Push alerts to all configured Apprise URLs. Returns count delivered."""
    if not alerts or not urls:
        return 0
    try:
        import apprise
    except ImportError:
        return 0

    client = apprise.Apprise()
    for url in urls:
        client.add(url)

    sent = 0
    for alert in alerts:
        title = _TITLES.get(alert.kind, "NetScan — alerta")
        if client.notify(title=title, body=alert.detail):
            sent += 1
    return sent
