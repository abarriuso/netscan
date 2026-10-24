"""Inventory diff: online tracking, port changes, gateway/conflict alerts,
uptime buckets and the device timeline.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

import json
from datetime import datetime, timedelta

from netscan.db.store import InventoryStore
from netscan.models import Device, DeviceMetrics, PortInfo, ScanResult

MAC = "aa:bb:cc:dd:ee:ff"
SCOPE = [22, 80, 443]


def _result(devices, network="192.168.1.0/24", ports_scanned=None, **kw) -> ScanResult:
    return ScanResult(
        network=network,
        total_devices=len(devices),
        devices=devices,
        ports_scanned=ports_scanned if ports_scanned is not None else SCOPE,
        **kw,
    )


def _dev(ip="192.168.1.50", ports=(), latency=1.0, **kw) -> Device:
    return Device(
        ip=ip, mac=kw.pop("mac", MAC), open_ports=[PortInfo(port=p) for p in ports], latency_ms=latency, **kw
    )


def test_offline_is_tracked_even_without_down_alerts():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([_dev()]))
    alerts = store.record_scan(_result([]))  # alert_on_down defaults to False
    assert alerts == []
    assert store.list_devices()[0].online is False
    kinds = [e.kind for e in store.device_events(mac=MAC)]
    assert kinds[0] == "down"


def test_back_online_raises_device_back_when_enabled():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([_dev()]))
    store.record_scan(_result([]), alert_on_down=True)
    alerts = store.record_scan(_result([_dev()]), alert_on_down=True)
    assert [a.kind for a in alerts] == ["device_back"]
    assert store.list_devices()[0].online is True


def test_scan_of_another_subnet_does_not_down_the_inventory():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([_dev()]))
    store.record_scan(_result([], network="10.0.0.0/24"), alert_on_down=True)
    assert store.list_devices()[0].online is True


def test_port_changes_raise_alert_and_closed_ports_are_removed():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([_dev(ports=[22, 80])]))
    alerts = store.record_scan(_result([_dev(ports=[22, 443])]))
    assert [a.kind for a in alerts] == ["ports_changed"]
    assert "opened 443" in alerts[0].detail and "closed 80" in alerts[0].detail
    stored = [p["port"] for p in json.loads(store.list_devices()[0].open_ports_json)]
    assert stored == [22, 443]


def test_ports_outside_the_probed_scope_are_kept():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([_dev(ports=[22, 8006])], ports_scanned=[22, 80, 443, 8006]))
    alerts = store.record_scan(_result([_dev(ports=[22])], ports_scanned=[22, 80, 443]))
    assert alerts == []  # 8006 was not probed this time: not "closed"
    stored = [p["port"] for p in json.loads(store.list_devices()[0].open_ports_json)]
    assert stored == [22, 8006]


def test_unresponsive_host_is_not_diffed():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([_dev(ports=[22, 80])]))
    alerts = store.record_scan(_result([_dev(ports=[], latency=None)]))
    assert alerts == []
    stored = [p["port"] for p in json.loads(store.list_devices()[0].open_ports_json)]
    assert stored == [22, 80]


def test_gateway_mac_change_is_flagged_once():
    store = InventoryStore("sqlite:///:memory:")
    gw = dict(gateway_ip="192.168.1.1")
    store.record_scan(_result([], gateway_mac="d4:86:60:f9:46:5e", **gw))
    alerts = store.record_scan(_result([], gateway_mac="66:66:66:66:66:66", **gw))
    assert [a.kind for a in alerts] == ["gateway_mac_changed"]
    assert "was d4:86:60:f9:46:5e" in alerts[0].detail
    assert store.record_scan(_result([], gateway_mac="66:66:66:66:66:66", **gw)) == []


def test_ip_conflict_is_reported_once_per_mac_set():
    store = InventoryStore("sqlite:///:memory:")
    dev = _dev(conflict_macs=["11:11:11:11:11:11"])
    first = store.record_scan(_result([dev]))
    assert "ip_conflict" in [a.kind for a in first]
    again = store.record_scan(_result([_dev(conflict_macs=["11:11:11:11:11:11"])]))
    assert "ip_conflict" not in [a.kind for a in again]


def test_speedtests_do_not_pollute_the_network_trend():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([_dev(metrics=DeviceMetrics(latency_avg_ms=1.0, quality=90))]))
    store.record_speedtest(MAC, DeviceMetrics(latency_avg_ms=50.0, quality=10))
    points = store.metrics_history()
    assert len(points) == 1
    assert points[0]["avg_latency_ms"] == 1.0


def test_uptime_buckets_merge_counters():
    store = InventoryStore("sqlite:///:memory:")
    start = datetime(2026, 10, 1, 12, 0)
    row = {
        "mac": MAC,
        "bucket_start": start,
        "probes": 10,
        "up": 9,
        "rtt_sum_ms": 9.0,
        "rtt_count": 9,
        "rtt_min_ms": 0.5,
        "rtt_max_ms": 2.0,
    }
    store.add_uptime([row])
    store.add_uptime(
        [
            {
                **row,
                "probes": 5,
                "up": 5,
                "rtt_sum_ms": 2.5,
                "rtt_count": 5,
                "rtt_min_ms": 0.3,
                "rtt_max_ms": 1.0,
            }
        ]
    )
    buckets = store.uptime_buckets(since=start - timedelta(hours=1))
    assert len(buckets) == 1
    b = buckets[0]
    assert (b.probes, b.up, b.rtt_count) == (15, 14, 14)
    assert b.rtt_min_ms == 0.3 and b.rtt_max_ms == 2.0


def test_set_device_state_writes_timeline():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([_dev()]))
    when = datetime.now()
    store.set_device_state(MAC, False, when, detail="down for test", method="")
    assert store.list_devices()[0].online is False
    ev = store.device_events(mac=MAC, kinds={"down"})[0]
    assert ev.detail == "down for test"


def test_trust_change_is_recorded_in_timeline():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([_dev()]))
    store.set_device_trusted(MAC, True)
    assert store.device_events(mac=MAC)[0].kind == "trusted"


def test_ack_all():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_result([_dev()]))
    store.record_scan(_result([_dev(mac="11:22:33:44:55:66", ip="192.168.1.60")]))
    assert store.acknowledge_all_alerts() == 2
    assert store.list_alerts(unacknowledged_only=True) == []
