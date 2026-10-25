"""In-process event bus: the live "what is NetScan doing right now" feed.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Every subsystem (scan engine, port scanner, nmap/rustscan wrappers, HTTP/TLS
fingerprint, live monitor, API middleware, integrations, toolbox) publishes
short, structured events here. The dashboard's terminal dock streams them
over ``/ws/events`` (replaying from a sequence number after a reconnect) and
``/api/events`` is the HTTP fallback.

Design notes:

* **Thread-safe, bounded.** Publishers run on scan/monitor worker threads;
  the buffer is a fixed-size ring (oldest events fall off), so a chatty scan
  can never grow memory without limit.
* **Monotonic ``seq``.** Clients ask for "everything after seq N"; a gap
  between the requested seq and the oldest buffered one tells them how many
  events they missed (``dropped``) instead of silently hiding it.
* **Persisted selectively.** Events at ``info`` and above are also written
  to the ``netscan.events`` logger (and so to ``netscan.log``); ``debug``
  events (every API call, every live-monitor tick) live only in the ring.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter, deque
from collections.abc import Callable
from datetime import datetime
from typing import Any

LEVELS = ("debug", "info", "warning", "error")
_LOG_LEVEL = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

# Logger that mirrors bus events into netscan.log. BusLogHandler skips it so
# an event is never fed back into the bus it came from.
_event_logger = logging.getLogger("netscan.events")

Event = dict[str, Any]
Subscriber = Callable[[Event], None]


class EventBus:
    """Bounded, thread-safe ring buffer of events with fan-out subscribers."""

    def __init__(self, capacity: int = 5000) -> None:
        self._buf: deque[Event] = deque(maxlen=capacity)
        self._seq = 0
        self._lock = threading.Lock()
        self._subscribers: set[Subscriber] = set()
        self.capacity = capacity
        self.counts: Counter[str] = Counter()
        self._recent: deque[float] = deque(maxlen=4096)  # publish times, for the rate

    def publish(self, source: str, msg: str, level: str = "info", **data: Any) -> Event:
        level = level if level in _LOG_LEVEL else "info"
        now = time.time()
        with self._lock:
            self._seq += 1
            event: Event = {
                "seq": self._seq,
                "ts": datetime.fromtimestamp(now).isoformat(timespec="milliseconds"),
                "level": level,
                "source": source,
                "msg": msg,
            }
            if data:
                event["data"] = data
            self._buf.append(event)
            self.counts[source] += 1
            self._recent.append(now)
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:  # a broken subscriber must not break the publisher
                logging.getLogger("netscan").debug("event subscriber failed", exc_info=True)
        # "log" events already came from a log record — mirroring them back
        # would write every line twice to netscan.log.
        if level != "debug" and source != "log":
            _event_logger.log(_LOG_LEVEL[level], "[%s] %s", source, msg)
        return event

    def since(self, seq: int = 0, limit: int = 500, sources: set[str] | None = None) -> dict[str, Any]:
        """Events with ``seq`` greater than the given one (oldest first)."""
        limit = max(1, min(limit, self.capacity))
        with self._lock:
            events = [e for e in self._buf if e["seq"] > seq]
            first = self._buf[0]["seq"] if self._buf else self._seq + 1
            last = self._seq
        if sources:
            events = [e for e in events if e["source"] in sources]
        # Events evicted from the ring between the client's seq and our oldest.
        dropped = max(0, first - seq - 1) if seq else 0
        return {"events": events[-limit:], "last_seq": last, "dropped": dropped}

    def subscribe(self, callback: Subscriber) -> Callable[[], None]:
        with self._lock:
            self._subscribers.add(callback)

        def _unsubscribe() -> None:
            with self._lock:
                self._subscribers.discard(callback)

        return _unsubscribe

    def stats(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            per_min = sum(1 for t in self._recent if now - t <= 60)
            return {
                "last_seq": self._seq,
                "buffered": len(self._buf),
                "capacity": self.capacity,
                "events_last_60s": per_min,
                "by_source": dict(self.counts),
            }

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()
            self.counts.clear()
            self._recent.clear()


bus = EventBus()


def emit(source: str, msg: str, level: str = "info", **data: Any) -> Event:
    """Publish an event on the process-wide bus (see module docstring)."""
    return bus.publish(source, msg, level, **data)


class BusLogHandler(logging.Handler):
    """Forward ordinary log records into the bus (source ``log``), so the
    terminal dock also shows warnings/tracebacks that never went through
    :func:`emit`. Records that came *from* the bus are skipped."""

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("netscan.events") or record.name == "uvicorn.access":
            return
        try:
            msg = record.getMessage()
            if record.exc_info and record.exc_info[1] is not None:
                msg = f"{msg} — {type(record.exc_info[1]).__name__}: {record.exc_info[1]}"
            level = (
                "error"
                if record.levelno >= logging.ERROR
                else (
                    "warning"
                    if record.levelno >= logging.WARNING
                    else ("info" if record.levelno >= logging.INFO else "debug")
                )
            )
            bus.publish("log", f"{record.name}: {msg}", level=level, logger=record.name)
        except Exception:
            self.handleError(record)


def fmt_ms(value: float | None) -> str:
    """Milliseconds with a precision that fits the magnitude (LAN RTTs are sub-ms)."""
    if value is None:
        return "—"
    if value < 1:
        return f"{value:.2f} ms"
    if value < 100:
        return f"{value:.1f} ms"
    return f"{value:.0f} ms"


def fmt_s(value: float) -> str:
    return f"{value:.2f} s" if value < 10 else f"{value:.1f} s"
