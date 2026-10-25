"""Continuous live network monitor.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

A background thread that probes every known device each ``interval_s``
seconds and turns the answers into:

* a rolling in-memory snapshot (per-device up/RTT/probe method, aggregate
  LAN latency series, gateway and Internet RTT) for the Live view;
* **state transitions** with hysteresis — a device is declared down after
  ``down_after`` consecutive failed ticks and up again on the first answer —
  written to the inventory (``online``/``last_seen``), the device timeline
  and, if enabled, as alerts;
* **uptime buckets**: probe counters aggregated per device over 5-minute
  buckets and flushed to SQLite, from which availability % (24 h / 7 d /
  30 d), outages and the uptime bars are computed.

Probe chain per device, cheapest first, stopping at the first answer:
ICMP echo → TCP connect() to up to 3 known open ports → ARP who-has
(Windows ``SendARP``, unprivileged; catches PCs whose firewall drops
everything). The method that answered is reported, so "up" is never a
mystery.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import fmean

from netscan.db.models import AlertRecord
from netscan.events import emit, fmt_ms
from netscan.scanner import icmp, speed

logger = logging.getLogger(__name__)

BUCKET_S = 300  # uptime bucket width (5 min)
_FLUSH_EVERY_S = 30.0
_ARP_RETRY_TICKS = 4  # a device already down is ARP-probed only every Nth tick (a miss costs ~4 s)


def _ip_key(ip: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in ip.split("."))
    except ValueError:
        return (999,)


def bucket_start(ts: datetime) -> datetime:
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - epoch % BUCKET_S)


@dataclass
class _DeviceState:
    up: bool | None = None  # None until the first decision
    since: datetime | None = None
    # False while `since` is only "when this monitor first saw the device":
    # the real start of the current state happened earlier, NetScan was not
    # watching. True once a transition was actually observed.
    since_exact: bool = False
    failures: int = 0
    last_method: str = ""
    last_rtt: float | None = None
    recent: deque = field(default_factory=lambda: deque(maxlen=120))  # (ts, up, rtt) — last ~10 min


@dataclass
class _Pending:
    probes: int = 0
    up: int = 0
    rtt_sum: float = 0.0
    rtt_n: int = 0
    rtt_min: float | None = None
    rtt_max: float | None = None


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
        down_after: int = 3,
        alert_on_change: bool = False,
        wan_targets: list[str] | None = None,
        gateway_ip: str | None = None,
    ) -> None:
        self._store = store
        self.interval_s = max(1.0, float(interval_s))
        self.ping_timeout = ping_timeout
        self.down_after = max(1, int(down_after))
        self.alert_on_change = alert_on_change
        self.wan_targets = list(wan_targets or [])
        self.gateway_ip = gateway_ip
        self._series: deque[dict] = deque(maxlen=buffer)
        self._devices: list[dict] = []
        self._updated_at: str | None = None
        self._max_devices = max_devices
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._states: dict[str, _DeviceState] = {}
        self._pending: dict[tuple[str, datetime], _Pending] = {}
        self._last_flush = time.monotonic()
        self._last_prune = 0.0
        self._ticks = 0
        self.last_tick_ms: float | None = None
        self.started_at = datetime.now()

    def start(self) -> None:
        emit(
            "live",
            f"live monitor started · every {self.interval_s:g} s · ICMP backend {icmp.backend()} · "
            f"down after {self.down_after} failed ticks · WAN targets {', '.join(self.wan_targets) or 'none'}",
        )
        threading.Thread(target=self._run, name="live-monitor", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self.flush()

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self._tick()
            except Exception:  # a bad tick must never kill the loop
                logger.exception("Live monitor tick failed")
            # Keep the cadence: sleep only what is left of the interval.
            self._stop.wait(max(0.5, self.interval_s - (time.monotonic() - started)))

    # ------------------------------------------------------------------ probes
    @staticmethod
    def _known_ports(dev) -> list[int]:
        try:
            return [int(p["port"]) for p in json.loads(dev.open_ports_json) if p.get("port")][:3]
        except (ValueError, AttributeError, TypeError, KeyError):
            return []

    def _probe(self, dev, allow_arp: bool) -> tuple[float | None, str]:
        """One reachability sample → (RTT ms or None, method that answered)."""
        rtt = icmp.echo(dev.ip, self.ping_timeout)
        if rtt is not None:
            return rtt, "icmp"
        for port in self._known_ports(dev):
            rtt = speed.tcp_connect_ms(dev.ip, port, timeout=self.ping_timeout)
            if rtt is not None:
                return rtt, f"tcp/{port}"
        # SendARP's own latency is OS-timer bound (~15.6 ms granularity on
        # Windows): it proves reachability but no RTT is reported for it.
        if allow_arp and dev.mac and icmp.arp_probe(dev.ip):
            return None, "arp"
        return None, ""

    def _probe_wan(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {}
        targets = ([self.gateway_ip] if self.gateway_ip else []) + self.wan_targets
        for target in targets:
            out[target] = icmp.echo(target, self.ping_timeout)
        return out

    # -------------------------------------------------------------------- tick
    def _tick(self) -> None:
        tick_start = time.perf_counter()
        self._ticks += 1
        devices = self._store.list_devices()[: self._max_devices]
        results: dict[str, tuple] = {}
        # Gateway/WAN are probed even with an empty inventory: "is the
        # Internet up?" must not depend on having scanned first.
        with ThreadPoolExecutor(max_workers=min(32, len(devices) + 1)) as ex:
            wan_future = ex.submit(self._probe_wan)
            futs = {}
            for d in devices:
                st = self._states.get(d.mac)
                allow_arp = st is None or st.up is not False or self._ticks % _ARP_RETRY_TICKS == 0
                futs[ex.submit(self._probe, d, allow_arp)] = d
            for fut in as_completed(futs):
                dev = futs[fut]
                try:
                    rtt, method = fut.result()
                except Exception:
                    rtt, method = None, ""
                results[dev.mac] = (dev, rtt, method)
            try:
                wan = wan_future.result()
            except Exception:
                wan = {}
        now = datetime.now()

        transitions = self._apply(results, now)
        self._accumulate(results, now)

        alive_rtts = [rtt for (_, rtt, method) in results.values() if rtt is not None]
        up_count = sum(1 for (_, _, method) in results.values() if method)
        agg = round(fmean(alive_rtts), 3) if alive_rtts else None
        gateway_ms = wan.get(self.gateway_ip) if self.gateway_ip else None
        wan_values = [wan.get(t) for t in self.wan_targets]
        wan_ok = [v for v in wan_values if v is not None]
        rows = []
        for mac, (dev, rtt, method) in results.items():
            st = self._states[mac]
            rows.append(
                {
                    "mac": mac,
                    "ip": dev.ip,
                    "name": dev.hostname or dev.mdns_name or dev.ip,
                    "vendor": dev.vendor,
                    "trusted": dev.trusted,
                    "up": bool(st.up),
                    "answered": bool(method),
                    "latency_ms": rtt,
                    "method": method,
                    "failures": st.failures,
                    "since": st.since.isoformat() if st.since else None,
                    "since_exact": st.since_exact,
                    "recent_up_pct": self._recent_pct(st),
                }
            )
        rows.sort(key=lambda r: (not r["up"], _ip_key(r["ip"])))
        self.last_tick_ms = round((time.perf_counter() - tick_start) * 1000, 1)
        wan_ms = round(fmean(wan_ok), 3) if wan_ok else None
        point = {
            "t": now.isoformat(timespec="seconds"),
            "latency_ms": agg,
            "online": up_count,
            "total": len(results),
            "gateway_ms": gateway_ms,
            "wan_ms": wan_ms,
            "wan_loss_pct": round(100 * (len(wan_values) - len(wan_ok)) / len(wan_values), 1)
            if wan_values
            else None,
            "tick_ms": self.last_tick_ms,
        }
        with self._lock:
            self._series.append(point)
            self._devices = rows
            self._updated_at = now.isoformat()

        emit(
            "live",
            f"tick #{self._ticks}: {up_count}/{len(results)} answering · LAN avg {fmt_ms(agg)}"
            + (f" · gateway {fmt_ms(gateway_ms)}" if self.gateway_ip else "")
            + (f" · WAN {fmt_ms(wan_ms)} ({point['wan_loss_pct']:.0f} % loss)" if wan_values else "")
            + f" · tick {self.last_tick_ms:.0f} ms",
            "debug",
            **{k: v for k, v in point.items() if k != "t"},
        )
        self._persist(transitions, [mac for mac, (_, _, m) in results.items() if m], now)

    def _apply(self, results: dict[str, tuple], now: datetime) -> list[tuple]:
        """Run the hysteresis state machine; return confirmed transitions."""
        transitions = []
        for mac, (dev, rtt, method) in results.items():
            st = self._states.get(mac)
            if st is None:
                # Seed from the inventory so a restart does not re-announce
                # every device as "up".
                st = _DeviceState(up=bool(dev.online), since=None)
                self._states[mac] = st
            st.recent.append((now, bool(method), rtt))
            st.last_method = method
            st.last_rtt = rtt
            if method:
                st.failures = 0
                if st.up is not True:
                    previous = st.up
                    st.up = True
                    st.since = now
                    st.since_exact = previous is False
                    if previous is False:
                        transitions.append((dev, True, method, rtt))
                elif st.since is None:
                    st.since = now
            else:
                st.failures += 1
                if st.up is not False and st.failures >= self.down_after:
                    st.up = False
                    st.since = now
                    st.since_exact = True
                    transitions.append((dev, False, "", None))
                elif st.up is False and st.since is None:
                    st.since = now
        return transitions

    @staticmethod
    def _recent_pct(st: _DeviceState) -> float | None:
        if not st.recent:
            return None
        return round(100 * sum(1 for _, ok, _ in st.recent if ok) / len(st.recent), 1)

    def _accumulate(self, results: dict[str, tuple], now: datetime) -> None:
        start = bucket_start(now)
        with self._lock:
            for mac, (_dev, rtt, method) in results.items():
                p = self._pending.setdefault((mac, start), _Pending())
                p.probes += 1
                if method:
                    p.up += 1
                if rtt is not None:
                    p.rtt_sum += rtt
                    p.rtt_n += 1
                    p.rtt_min = rtt if p.rtt_min is None else min(p.rtt_min, rtt)
                    p.rtt_max = rtt if p.rtt_max is None else max(p.rtt_max, rtt)

    def _persist(self, transitions: list[tuple], answered: list[str], now: datetime) -> None:
        alerts: list[AlertRecord] = []
        for dev, up, method, rtt in transitions:
            label = dev.hostname or dev.mdns_name or dev.vendor or dev.mac
            if up:
                msg = f"▲ {dev.ip} ({label}) is UP again via {method}" + (
                    f" · {fmt_ms(rtt)}" if rtt is not None else ""
                )
                emit("live", msg, "info", host=dev.ip, mac=dev.mac, state="up")
            else:
                msg = f"▼ {dev.ip} ({label}) is DOWN — no ICMP, TCP or ARP answer for {self.down_after} ticks"
                emit("live", msg, "warning", host=dev.ip, mac=dev.mac, state="down")
            try:
                self._store.set_device_state(dev.mac, up, now, detail=msg, method=method)
            except Exception:
                logger.exception("Could not persist the state of %s", dev.mac)
            if self.alert_on_change:
                alerts.append(
                    AlertRecord(
                        kind="device_back" if up else "device_down",
                        device_mac=dev.mac,
                        device_ip=dev.ip,
                        detail=msg,
                    )
                )
        if alerts:
            try:
                self._store.add_alerts(alerts)
            except Exception:
                logger.exception("Could not store live alerts")
        if time.monotonic() - self._last_flush >= _FLUSH_EVERY_S:
            self.flush(answered=answered, now=now)

    def flush(self, answered: list[str] | None = None, now: datetime | None = None) -> None:
        """Write the pending uptime counters (and last_seen bumps) to the DB."""
        with self._lock:
            pending, self._pending = self._pending, {}
        self._last_flush = time.monotonic()
        rows = [
            {
                "mac": mac,
                "bucket_start": start,
                "probes": p.probes,
                "up": p.up,
                "rtt_sum_ms": p.rtt_sum,
                "rtt_count": p.rtt_n,
                "rtt_min_ms": p.rtt_min,
                "rtt_max_ms": p.rtt_max,
            }
            for (mac, start), p in pending.items()
        ]
        try:
            self._store.add_uptime(rows)
            if answered:
                self._store.touch_devices(answered, now or datetime.now())
            if time.monotonic() - self._last_prune > 3600:
                self._last_prune = time.monotonic()
                self._store.prune_live()
        except Exception:
            logger.exception("Could not flush uptime counters")
            # Put them back so the next flush retries instead of losing data.
            with self._lock:
                for (mac, start), p in pending.items():
                    self._pending.setdefault((mac, start), p)

    def pending_rows(self) -> list[dict[str, object]]:
        """Unflushed counters, so API reads include the current bucket."""
        with self._lock:
            return [
                {
                    "mac": mac,
                    "bucket_start": start,
                    "probes": p.probes,
                    "up": p.up,
                    "rtt_sum_ms": p.rtt_sum,
                    "rtt_count": p.rtt_n,
                    "rtt_min_ms": p.rtt_min,
                    "rtt_max_ms": p.rtt_max,
                }
                for (mac, start), p in self._pending.items()
            ]

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "series": list(self._series),
                "devices": list(self._devices),
                "online": sum(1 for d in self._devices if d["up"]),
                "total": len(self._devices),
                "interval_s": self.interval_s,
                "updated_at": self._updated_at,
                "down_after": self.down_after,
                "icmp_backend": icmp.backend(),
                "gateway_ip": self.gateway_ip,
                "wan_targets": self.wan_targets,
                "tick_ms": self.last_tick_ms,
                "monitoring_since": self.started_at.isoformat(timespec="seconds"),
            }


def window_start(hours: float, now: datetime | None = None) -> datetime:
    return (now or datetime.now()) - timedelta(hours=hours)
