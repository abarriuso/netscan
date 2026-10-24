"""Live monitor state machine + uptime/outage/IP-map/security analytics.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from datetime import datetime, timedelta

from netscan import insights
from netscan.db.store import InventoryStore
from netscan.live import BUCKET_S, LiveMonitor, bucket_start
from netscan.models import Device, PortInfo, ScanResult

MAC = "aa:bb:cc:dd:ee:01"


def _store_with_device(tmp_path, ports=(22,)) -> InventoryStore:
    store = InventoryStore(f"sqlite:///{tmp_path / 'live.db'}")
    store.record_scan(
        ScanResult(
            network="192.168.1.0/24",
            devices=[
                Device(
                    ip="192.168.1.10", mac=MAC, latency_ms=1.0, open_ports=[PortInfo(port=p) for p in ports]
                )
            ],
            ports_scanned=[22, 80],
        )
    )
    return store


def _monitor(store, answers):
    lm = LiveMonitor(store, interval_s=5, ping_timeout=0.1, down_after=3)
    seq = iter(answers)
    lm._probe = lambda dev, allow_arp: next(seq)  # type: ignore[method-assign]
    lm._probe_wan = lambda: {}  # type: ignore[method-assign]
    return lm


def test_bucket_alignment():
    t = datetime(2026, 10, 1, 12, 7, 31)
    assert bucket_start(t) == datetime(2026, 10, 1, 12, 5, 0)
    assert BUCKET_S == 300


def test_hysteresis_declares_down_after_n_failures_and_up_on_first_answer(tmp_path):
    store = _store_with_device(tmp_path)
    lm = _monitor(store, [(0.4, "icmp"), (None, ""), (None, ""), (None, ""), (None, ""), (1.2, "tcp/22")])
    lm._tick()
    lm._tick()
    lm._tick()
    assert store.list_devices()[0].online is True  # 2 failures: still up
    lm._tick()  # 3rd consecutive failure → down
    assert store.list_devices()[0].online is False
    lm._tick()
    lm._tick()  # first answer → up again
    assert store.list_devices()[0].online is True
    kinds = [e.kind for e in store.device_events(mac=MAC, kinds={"up", "down"})]
    assert kinds[:2] == ["up", "down"]  # newest first
    snap = lm.snapshot()
    assert snap["devices"][0]["method"] == "tcp/22"
    assert snap["devices"][0]["up"] is True


def test_live_alerts_only_when_enabled(tmp_path):
    store = _store_with_device(tmp_path)
    lm = _monitor(store, [(None, "")] * 3)
    lm.alert_on_change = True
    for _ in range(3):
        lm._tick()
    assert [a.kind for a in store.list_alerts() if a.kind.startswith("device_")] == ["device_down"]


def test_arp_only_answer_counts_as_up_without_rtt(tmp_path):
    store = _store_with_device(tmp_path)
    lm = _monitor(store, [(None, "arp")])
    lm._tick()
    row = lm.snapshot()["devices"][0]
    assert row["up"] is True and row["latency_ms"] is None and row["method"] == "arp"


def test_uptime_report_counts_pending_and_flushed_probes(tmp_path):
    store = _store_with_device(tmp_path)
    lm = _monitor(store, [(0.5, "icmp")] * 3 + [(None, "")])
    for _ in range(4):
        lm._tick()
    report = insights.uptime_report(store, lm, hours=1, slots=6, interval_s=5)
    dev = report["devices"][0]
    assert dev["windows"]["1h"]["probes"] == 4
    assert dev["windows"]["1h"]["availability_pct"] == 75.0
    lm.flush()
    report = insights.uptime_report(store, lm, hours=1, slots=6, interval_s=5)
    assert report["devices"][0]["windows"]["1h"]["probes"] == 4  # same data, now from SQLite
    assert report["devices"][0]["windows"]["1h"]["coverage_pct"] == round(100 * 4 / 720, 1)
    last_slot = report["devices"][0]["timeline"][-1]
    assert last_slot["probes"] == 4
    assert last_slot["rtt_avg_ms"] == 0.5


def test_outages_pairs_and_ongoing():
    now = datetime(2026, 10, 2, 12, 0)

    class E:
        def __init__(self, kind, at):
            self.kind, self.created_at = kind, at

    evs = [
        E("down", now - timedelta(hours=5)),
        E("up", now - timedelta(hours=4, minutes=30)),
        E("down", now - timedelta(minutes=10)),
    ]
    out = insights._outages(evs, now)
    assert [o["duration_s"] for o in out] == [1800, 600]
    assert out[-1]["ongoing"] is True and out[-1]["end"] is None


def test_ip_map_states_and_utilization(tmp_path):
    store = _store_with_device(tmp_path)
    data = insights.ip_map("192.168.1.0/28", store, gateway_ip="192.168.1.1", local_ip="192.168.1.2")
    states = {c["ip"]: c["state"] for c in data["cells"]}
    assert states["192.168.1.0"] == "network"
    assert states["192.168.1.15"] == "broadcast"
    assert states["192.168.1.1"] == "gateway"
    assert states["192.168.1.2"] == "self"
    assert states["192.168.1.10"] == "online"
    assert data["usable"] == 14
    assert data["used"] == 3
    assert data["utilization_pct"] == round(100 * 3 / 14, 1)


def test_ip_map_rejects_big_networks(tmp_path):
    import pytest

    store = _store_with_device(tmp_path)
    with pytest.raises(ValueError):
        insights.ip_map("10.0.0.0/16", store, None, None)


def test_security_report_and_map(tmp_path):
    store = _store_with_device(tmp_path, ports=(22, 23))
    report = insights.security_report(store, None, "192.168.1.1", "192.168.1.2")
    dev = report["devices"][0]
    assert dev["score"] >= 45  # untrusted (15) + new (10) + telnet (30)
    assert report["exposure"] == [{"port": 23, "devices": 1}]
    m = insights.network_map(store, None, None, "192.168.1.1", "192.168.1.2")
    roles = {n["role"] for n in m["nodes"]}
    assert {"gateway", "netscan"} <= roles  # synthesized when not in the inventory
    assert len(m["edges"]) == len(m["nodes"]) - 1


def test_prometheus_exposition_format(tmp_path):
    store = _store_with_device(tmp_path)

    class State:
        pass

    state = State()
    state.store = store
    state.live = None
    state.scans_completed = 3
    state.last_scan_duration_s = 12.5
    text = insights.prometheus(state, None)
    assert "# TYPE netscan_device_up gauge" in text
    assert 'netscan_device_up{mac="aa:bb:cc:dd:ee:01",ip="192.168.1.10",name="192.168.1.10"} 1' in text
    assert "netscan_scans_completed_total 3" in text
    assert text.endswith("\n")
