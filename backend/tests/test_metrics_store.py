"""Tests for metric persistence in the inventory store + API endpoints.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

from netscan.db.store import InventoryStore
from netscan.models import Device, DeviceMetrics, ScanResult


def _store(tmp_path) -> InventoryStore:
    return InventoryStore(f"sqlite:///{tmp_path / 'test.db'}", str(tmp_path))


def test_record_scan_persists_metrics_and_samples(tmp_path):
    store = _store(tmp_path)
    dev = Device(
        ip="192.168.1.10",
        mac="aa:bb:cc:dd:ee:ff",
        metrics=DeviceMetrics(
            latency_avg_ms=3.0,
            jitter_ms=0.4,
            packet_loss_pct=0.0,
            tcp_connect_avg_ms=5.0,
            quality=97,
        ),
    )
    result = ScanResult(network="192.168.1.0/24", total_devices=1, devices=[dev])
    store.record_scan(result)

    records = store.list_devices()
    assert len(records) == 1
    rec = records[0]
    assert rec.quality == 97
    assert rec.jitter_ms == 0.4
    assert rec.tcp_connect_avg_ms == 5.0

    samples = store.metric_samples("aa:bb:cc:dd:ee:ff")
    assert len(samples) == 1
    assert samples[0].quality == 97


def test_metrics_summary_aggregates(tmp_path):
    store = _store(tmp_path)
    devs = [
        Device(
            ip="192.168.1.1",
            mac="aa:00:00:00:00:01",
            metrics=DeviceMetrics(latency_avg_ms=2.0, packet_loss_pct=0.0, quality=90),
        ),
        Device(
            ip="192.168.1.2",
            mac="aa:00:00:00:00:02",
            metrics=DeviceMetrics(latency_avg_ms=4.0, packet_loss_pct=10.0, quality=70),
        ),
    ]
    store.record_scan(ScanResult(total_devices=2, devices=devs))
    summary = store.metrics_summary()
    assert summary["devices_total"] == 2
    assert summary["avg_quality"] == 80
    assert summary["worst_quality"] == 70
    assert summary["avg_latency_ms"] == 3.0


def test_record_speedtest_updates_device(tmp_path):
    store = _store(tmp_path)
    dev = Device(ip="192.168.1.20", mac="bb:bb:bb:bb:bb:bb")
    store.record_scan(ScanResult(total_devices=1, devices=[dev]))

    m = DeviceMetrics(latency_avg_ms=1.5, jitter_ms=0.2, packet_loss_pct=0.0, quality=99)
    assert store.record_speedtest("bb:bb:bb:bb:bb:bb", m) is True
    rec = store.device_by_mac("bb:bb:bb:bb:bb:bb")
    assert rec is not None and rec.quality == 99
    # Unknown device -> False
    assert store.record_speedtest("00:00:00:00:00:00", m) is False


def test_migration_adds_columns_to_legacy_db(tmp_path):
    """A pre-metrics 'devices' table gets the new columns added, not wiped."""
    import sqlite3

    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE devices (id INTEGER PRIMARY KEY, mac TEXT, ip TEXT, "
        "hostname TEXT, vendor TEXT, mdns_name TEXT, os_guess TEXT, notes TEXT, "
        "trusted BOOLEAN, first_seen TIMESTAMP, last_seen TIMESTAMP, "
        "last_latency_ms FLOAT, open_ports_json TEXT, online BOOLEAN)"
    )
    conn.execute("INSERT INTO devices (mac, ip, online) VALUES ('ca:fe:ca:fe:ca:fe', '10.0.0.1', 1)")
    conn.commit()
    conn.close()

    store = InventoryStore(f"sqlite:///{db}", str(tmp_path))
    # New columns are now present and the old row survives.
    rec = store.device_by_mac("ca:fe:ca:fe:ca:fe")
    assert rec is not None
    assert rec.quality is None  # column exists, value defaulted
