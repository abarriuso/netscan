"""Regression tests for the LXC runtime issues: Linux L2 presence without
flapping, offset-carrying timestamps, and the uptime report's cost.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

import time
from datetime import datetime, timedelta

from sqlmodel import Session

from netscan import events, insights, live
from netscan.db.models import UptimeBucket
from netscan.db.store import InventoryStore
from netscan.live import HOLD, LiveMonitor
from netscan.models import Device, ScanResult
from netscan.scanner import discovery
from netscan.timeutil import iso, localize

MAC = "aa:bb:cc:dd:ee:01"

IP_NEIGH = """192.168.1.1 dev eth0 lladdr d4:86:60:f9:46:5e router REACHABLE
192.168.1.10 dev eth0 lladdr aa:bb:cc:dd:ee:01 STALE
192.168.1.11 dev eth0 FAILED
192.168.1.12 dev eth0 lladdr AA:BB:CC:DD:EE:12 DELAY
fe80::1 dev eth0 lladdr d4:86:60:f9:46:5e router STALE
"""


def test_parse_ip_neigh():
    table = discovery.parse_ip_neigh(IP_NEIGH)
    assert table["192.168.1.1"] == ("d4:86:60:f9:46:5e", "REACHABLE")
    assert table["192.168.1.10"] == (MAC, "STALE")
    assert table["192.168.1.11"] == ("", "FAILED")
    assert table["192.168.1.12"] == ("aa:bb:cc:dd:ee:12", "DELAY")
    assert "fe80::1" not in table


def _monitor(tmp_path, answers, neigh):
    store = InventoryStore(f"sqlite:///{tmp_path / 'l.db'}")
    store.record_scan(
        ScanResult(network="192.168.1.0/24", devices=[Device(ip="192.168.1.10", mac=MAC, latency_ms=1.0)])
    )
    lm = LiveMonitor(store, interval_s=5, ping_timeout=0.1, down_after=3)
    seq = iter(answers)
    lm._probe = lambda dev, allow_arp: next(seq)  # type: ignore[method-assign]
    lm._probe_wan = lambda: {}  # type: ignore[method-assign]
    states = iter(neigh)
    return store, lm, states


def test_kernel_reachable_keeps_a_silent_device_up(tmp_path, monkeypatch):
    monkeypatch.setattr(live.icmp, "IS_WINDOWS", False)
    store, lm, states = _monitor(tmp_path, [(None, "")] * 5, [{"192.168.1.10": (MAC, "REACHABLE")}] * 5)
    monkeypatch.setattr(live.discovery, "neighbor_states", lambda: next(states))
    for _ in range(5):
        lm._tick()
    row = lm.snapshot()["devices"][0]
    assert row["up"] is True and row["method"] == "arp-cache"
    assert store.list_devices()[0].online is True


def test_unconfirmed_l2_state_neither_counts_up_nor_down(tmp_path, monkeypatch):
    """STALE/DELAY/PROBE ticks are skipped: a power-saving phone that
    alternates 'no ICMP' with 'kernel still verifying' must not flap."""
    monkeypatch.setattr(live.icmp, "IS_WINDOWS", False)
    neigh = [{"192.168.1.10": (MAC, "STALE")}, {"192.168.1.10": (MAC, "DELAY")}] * 3
    store, lm, states = _monitor(tmp_path, [(None, "")] * 6, neigh)
    monkeypatch.setattr(live.discovery, "neighbor_states", lambda: next(states))
    for _ in range(6):
        lm._tick()
    assert store.list_devices()[0].online is True
    assert lm.snapshot()["devices"][0]["method"] == HOLD
    assert lm.pending_rows() == []  # no verdict → no probe counted against uptime


def test_failed_neighbour_still_goes_down(tmp_path, monkeypatch):
    monkeypatch.setattr(live.icmp, "IS_WINDOWS", False)
    store, lm, states = _monitor(tmp_path, [(None, "")] * 3, [{"192.168.1.10": ("", "FAILED")}] * 3)
    monkeypatch.setattr(live.discovery, "neighbor_states", lambda: next(states))
    for _ in range(3):
        lm._tick()
    assert store.list_devices()[0].online is False


def test_timestamps_carry_the_server_offset():
    naive = datetime(2026, 10, 27, 10, 0, 0)
    out = iso(naive)
    assert out is not None and out.startswith("2026-10-27T10:00:00") and ("+" in out[19:] or "-" in out[19:])
    assert datetime.fromisoformat(out).tzinfo is not None
    nested = localize({"a": [naive, {"b": naive}], "c": 1})
    assert nested["a"][0] == out and nested["a"][1]["b"] == out and nested["c"] == 1
    ev = events.emit("test", "tz check")
    assert datetime.fromisoformat(ev["ts"]).tzinfo is not None


def test_uptime_report_stays_fast_with_a_month_of_history(tmp_path):
    store = InventoryStore(f"sqlite:///{tmp_path / 'u.db'}")
    devs = [Device(ip=f"192.168.1.{i}", mac=f"aa:bb:cc:dd:ee:{i:02x}", latency_ms=1.0) for i in range(2, 22)]
    store.record_scan(ScanResult(network="192.168.1.0/24", devices=devs))
    now = datetime.now()
    starts = [now - timedelta(minutes=5 * i) for i in range(8640)]  # 30 days
    with Session(store.engine) as s:
        s.add_all(
            [
                UptimeBucket(
                    device_mac=d.mac, bucket_start=b, probes=60, up=60, rtt_sum_ms=30.0, rtt_count=60
                )
                for b in starts
                for d in devs
            ]
        )
        s.commit()
    t0 = time.perf_counter()
    report = insights.uptime_report(store, None, hours=24, slots=48, now=now)
    elapsed = time.perf_counter() - t0
    assert report["devices"][0]["windows"]["30d"]["probes"] == 8640 * 60
    assert report["devices"][0]["windows"]["24h"]["availability_pct"] == 100.0
    # Was ~4 s before the covering index + single-pass binning.
    assert elapsed < 1.5, f"uptime report took {elapsed:.2f} s"
