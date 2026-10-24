"""Event bus tests.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

import logging
import threading

from netscan import events
from netscan.events import EventBus, fmt_ms


def test_publish_assigns_monotonic_seq_and_fields():
    bus = EventBus(capacity=10)
    a = bus.publish("scan", "hello", host="10.0.0.1")
    b = bus.publish("ports", "open", "warning")
    assert b["seq"] == a["seq"] + 1
    assert a["data"] == {"host": "10.0.0.1"}
    assert b["level"] == "warning"
    assert "T" in a["ts"]


def test_since_returns_only_newer_events_and_reports_drops():
    bus = EventBus(capacity=5)
    for i in range(12):
        bus.publish("scan", f"e{i}")
    out = bus.since(3)
    # Ring keeps seq 8..12; the client asked from 3 → 4 events (4..7) lost.
    assert [e["seq"] for e in out["events"]] == [8, 9, 10, 11, 12]
    assert out["dropped"] == 4
    assert out["last_seq"] == 12
    assert bus.since(12)["events"] == []


def test_since_filters_by_source():
    bus = EventBus()
    bus.publish("scan", "a")
    bus.publish("api", "b")
    out = bus.since(0, sources={"api"})
    assert [e["msg"] for e in out["events"]] == ["b"]


def test_subscriber_errors_do_not_break_publisher():
    bus = EventBus()
    got = []
    bus.subscribe(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    unsubscribe = bus.subscribe(got.append)
    bus.publish("x", "1")
    unsubscribe()
    bus.publish("x", "2")
    assert [e["msg"] for e in got] == ["1"]


def test_thread_safety_under_concurrent_publishers():
    bus = EventBus(capacity=10000)

    def worker():
        for _ in range(500):
            bus.publish("t", "m")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    seqs = [e["seq"] for e in bus.since(0, limit=10000)["events"]]
    assert len(seqs) == 4000
    assert seqs == sorted(set(seqs))


def test_log_handler_forwards_warnings_but_not_bus_echoes():
    before = events.bus.stats()["last_seq"]
    handler = events.BusLogHandler(level=logging.WARNING)
    log = logging.getLogger("netscan.testing")
    log.addHandler(handler)
    try:
        log.warning("disk almost full")
        logging.getLogger("netscan.events").warning("[x] echo")  # must be ignored
    finally:
        log.removeHandler(handler)
    new = events.bus.since(before)["events"]
    assert any(e["source"] == "log" and "disk almost full" in e["msg"] for e in new)
    assert not any("echo" in e["msg"] for e in new)


def test_fmt_ms_precision_follows_magnitude():
    assert fmt_ms(None) == "—"
    assert fmt_ms(0.4123) == "0.41 ms"
    assert fmt_ms(12.345) == "12.3 ms"
    assert fmt_ms(250.4) == "250 ms"
