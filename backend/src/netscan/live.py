"""Continuous live network monitor.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

A lightweight background thread that pings the known devices every few
seconds and keeps an in-memory, rolling snapshot: a per-device up/latency
map plus an aggregate latency series. This is the "real-time" pulse of the
network, independent of the heavier per-scan history kept in the database.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from statistics import fmean

from netscan.scanner import speed

logger = logging.getLogger(__name__)


def _ip_key(ip: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in ip.split("."))
    except ValueError:
        return (999,)


class LiveMonitor:
    """Polls known devices on a fixed cadence; exposes a rolling snapshot."""

    def __init__(
        self,
        store,
        *,
        interval_s: float = 5.0,
        ping_timeout: float = 1.0,
        buffer: int = 180,
        max_devices: int = 80,
    ) -> None:
        self._store = store
        self.interval_s = max(1.0, float(interval_s))
        self.ping_timeout = ping_timeout
        self._series: deque[dict] = deque(maxlen=buffer)
        self._devices: list[dict] = []
        self._updated_at: str | None = None
        self._max_devices = max_devices
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._run, name="live-monitor", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:  # a bad tick must never kill the loop
                logger.exception("Fallo en el tick del monitor en vivo")
            self._stop.wait(self.interval_s)

    def _first_port(self, dev) -> int | None:
        try:
            for p in json.loads(dev.open_ports_json):
                port = p.get("port")
                if port:
                    return int(port)
        except (ValueError, AttributeError, TypeError):
            pass
        return None

    def _probe(self, dev) -> float | None:
        """One RTT sample: ICMP first, TCP-connect to a known port as fallback."""
        lat = speed._ping_once(dev.ip, self.ping_timeout)
        if lat is None:
            port = self._first_port(dev)
            if port is not None:
                lat = speed.tcp_connect_ms(dev.ip, port, timeout=self.ping_timeout)
        return lat

    def _tick(self) -> None:
        devices = self._store.list_devices()[: self._max_devices]
        results: dict[str, tuple] = {}
        if devices:
            with ThreadPoolExecutor(max_workers=min(24, len(devices))) as ex:
                futs = {ex.submit(self._probe, d): d for d in devices}
                for fut in as_completed(futs):
                    dev = futs[fut]
                    try:
                        lat = fut.result()
                    except Exception:
                        lat = None
                    results[dev.mac] = (dev, lat)
        now = datetime.now()
        alive = [lat for (_, lat) in results.values() if lat is not None]
        agg = round(fmean(alive), 2) if alive else None
        rows = [
            {
                "mac": mac,
                "ip": dev.ip,
                "name": dev.hostname or dev.mdns_name or dev.ip,
                "vendor": dev.vendor,
                "trusted": dev.trusted,
                "up": lat is not None,
                "latency_ms": lat,
            }
            for mac, (dev, lat) in results.items()
        ]
        rows.sort(key=lambda r: (not r["up"], _ip_key(r["ip"])))
        with self._lock:
            self._series.append({"t": now.isoformat(), "latency_ms": agg, "online": len(alive)})
            self._devices = rows
            self._updated_at = now.isoformat()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "series": list(self._series),
                "devices": list(self._devices),
                "online": sum(1 for d in self._devices if d["up"]),
                "total": len(self._devices),
                "interval_s": self.interval_s,
                "updated_at": self._updated_at,
            }
