"""Inventory store diff/alert tests.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from netscan.db.store import InventoryStore
from netscan.models import Device, ScanResult


def _result(devices: list[Device]) -> ScanResult:
    return ScanResult(
        network="192.168.1.0/24",
        total_devices=len(devices),
        devices=devices,
    )


def test_new_device_alert():
    store = InventoryStore("sqlite:///:memory:")
    result = _result([Device(ip="192.168.1.50", mac="aa:bb:cc:dd:ee:ff")])
    alerts = store.record_scan(result)
    assert len(alerts) == 1
    assert alerts[0].kind == "new_device"
    assert result.devices[0].is_new is True


def test_known_device_no_alert_and_ip_change_alert():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([Device(ip="192.168.1.50", mac="aa:bb:cc:dd:ee:ff")]))

    # Same device, same IP → no alerts
    alerts = store.record_scan(_result([Device(ip="192.168.1.50", mac="aa:bb:cc:dd:ee:ff")]))
    assert alerts == []

    # Same MAC, new IP → mac_changed alert
    alerts = store.record_scan(_result([Device(ip="192.168.1.77", mac="aa:bb:cc:dd:ee:ff")]))
    assert len(alerts) == 1
    assert alerts[0].kind == "mac_changed"
    assert alerts[0].device_ip == "192.168.1.77"


def test_device_down_alert():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([Device(ip="192.168.1.50", mac="aa:bb:cc:dd:ee:ff")]))
    alerts = store.record_scan(_result([]), alert_on_down=True)
    assert any(a.kind == "device_down" for a in alerts)
    device = store.list_devices()[0]
    assert device.online is False


def test_trust_and_ack():
    store = InventoryStore("sqlite:///:memory:")
    alerts = store.record_scan(_result([Device(ip="192.168.1.50", mac="aa:bb:cc:dd:ee:ff")]))
    assert store.set_device_trusted("aa:bb:cc:dd:ee:ff", True, notes="Mi NAS")
    assert store.list_devices()[0].trusted is True
    assert store.list_devices()[0].notes == "Mi NAS"
    assert store.acknowledge_alert(alerts[0].id)  # type: ignore[arg-type]
    assert store.list_alerts(unacknowledged_only=True) == []


def test_last_scan_recorded():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([Device(ip="192.168.1.50", mac="aa:bb:cc:dd:ee:ff")]))
    last = store.last_scan()
    assert last is not None
    assert last.total_devices == 1
