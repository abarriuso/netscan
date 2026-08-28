"""Tests for the speed / quality metrics module.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import socket

from netscan.models import DeviceMetrics, PortInfo
from netscan.scanner import speed


def test_latency_stats_all_lost(monkeypatch):
    monkeypatch.setattr(speed, "_ping_once", lambda ip, timeout: None)
    stats = speed.latency_stats("10.0.0.1", count=4)
    assert stats["packet_loss_pct"] == 100.0
    assert stats["latency_avg_ms"] is None
    assert stats["jitter_ms"] is None


def test_latency_stats_computes_avg_and_jitter(monkeypatch):
    seq = iter([10.0, 20.0, 30.0, 40.0])
    monkeypatch.setattr(speed, "_ping_once", lambda ip, timeout: next(seq))
    stats = speed.latency_stats("10.0.0.1", count=4)
    assert stats["latency_avg_ms"] == 25.0
    assert stats["latency_min_ms"] == 10.0
    assert stats["latency_max_ms"] == 40.0
    assert stats["packet_loss_pct"] == 0.0
    # successive diffs are all 10 -> jitter 10
    assert stats["jitter_ms"] == 10.0


def test_latency_stats_partial_loss(monkeypatch):
    seq = iter([12.0, None, 18.0, None])
    monkeypatch.setattr(speed, "_ping_once", lambda ip, timeout: next(seq))
    stats = speed.latency_stats("10.0.0.1", count=4)
    assert stats["packet_loss_pct"] == 50.0
    assert stats["latency_avg_ms"] == 15.0


def test_tcp_connect_ms_open_port():
    # A real listening socket on loopback => handshake succeeds and is timed.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        ms = speed.tcp_connect_ms("127.0.0.1", port, timeout=1.0)
        assert ms is not None and ms >= 0
    finally:
        srv.close()


def test_tcp_connect_ms_closed_port():
    # An unbound high port should refuse quickly -> None.
    assert speed.tcp_connect_ms("127.0.0.1", 1, timeout=0.3) is None


def test_port_connect_times_mixed():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        result = speed.port_connect_times("127.0.0.1", [port, 1], timeout=0.4)
        assert port in result
        assert 1 not in result  # refused
    finally:
        srv.close()


def test_quality_score_perfect():
    m = DeviceMetrics(latency_avg_ms=0.5, jitter_ms=0.0, packet_loss_pct=0.0)
    assert speed.quality_score(m) == 100


def test_quality_score_degrades_with_loss():
    good = DeviceMetrics(latency_avg_ms=1.0, jitter_ms=0.0, packet_loss_pct=0.0)
    bad = DeviceMetrics(latency_avg_ms=1.0, jitter_ms=0.0, packet_loss_pct=50.0)
    assert speed.quality_score(bad) < speed.quality_score(good)
    assert 0 <= speed.quality_score(bad) <= 100


def test_measure_device_integration(monkeypatch):
    monkeypatch.setattr(
        speed,
        "latency_stats",
        lambda ip, count, timeout: {
            "latency_avg_ms": 2.0,
            "latency_min_ms": 1.0,
            "latency_max_ms": 3.0,
            "jitter_ms": 0.5,
            "packet_loss_pct": 0.0,
        },
    )
    monkeypatch.setattr(speed, "port_connect_times", lambda ip, ports, **kw: {80: 4.0, 443: 6.0})
    m = speed.measure_device("10.0.0.5", [PortInfo(port=80), PortInfo(port=443)], count=3)
    assert m.latency_avg_ms == 2.0
    assert m.tcp_connect_avg_ms == 5.0
    assert m.quality is not None and 0 <= m.quality <= 100


def test_measure_device_no_ports(monkeypatch):
    monkeypatch.setattr(
        speed,
        "latency_stats",
        lambda ip, count, timeout: {
            "latency_avg_ms": None,
            "latency_min_ms": None,
            "latency_max_ms": None,
            "jitter_ms": None,
            "packet_loss_pct": 100.0,
        },
    )
    m = speed.measure_device("10.0.0.9", [], count=2)
    assert m.tcp_connect_ms == {}
    assert m.tcp_connect_avg_ms is None
