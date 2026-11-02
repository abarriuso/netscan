"""Inventory store: persists scans, diffs devices, raises alerts.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import ipaddress
import json
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import delete, event, func, inspect, text
from sqlalchemy import select as sa_select
from sqlmodel import Session, SQLModel, create_engine, select

from netscan.db.models import (
    AlertRecord,
    DeviceEvent,
    DeviceRecord,
    IntegrationInstance,
    MetaRecord,
    MetricSample,
    ScanRecord,
    UptimeBucket,
)
from netscan.events import emit
from netscan.models import Device, ScanResult
from netscan.timeutil import iso

# How many historical scans to keep in the DB (oldest are pruned).
SCAN_RETENTION = 200
# How many metric samples to keep per device (oldest pruned).
METRIC_RETENTION = 500
# Live-monitor uptime buckets (5 min each) are kept this long.
UPTIME_RETENTION = timedelta(days=35)
# Device timeline events are kept this long.
EVENT_RETENTION = timedelta(days=365)

AddEvent = Callable[..., None]


def _in_network(ip: str, network: str) -> bool:
    try:
        return ipaddress.IPv4Address(ip) in ipaddress.IPv4Network(network, strict=False)
    except ValueError:
        return False


class InventoryStore:
    def __init__(self, db_url: str, data_dir: str | None = None) -> None:
        if data_dir:
            from pathlib import Path

            Path(data_dir).mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(db_url, echo=False)
        # Serializes read-modify-write sequences (uptime upserts from the live
        # monitor vs. a scan being recorded) that SQLite would interleave.
        self._write_lock = threading.RLock()
        if db_url.startswith("sqlite"):
            self._setup_sqlite_pragmas()
        SQLModel.metadata.create_all(self.engine)
        self._migrate()

    def _migrate(self) -> None:
        """Additively add columns introduced after the first release.

        SQLModel.create_all() creates missing tables but never ALTERs an
        existing one, so a DB from an older NetScan would be missing the new
        metric columns. We add them idempotently instead of forcing a wipe.
        """
        new_columns = {
            "devices": {
                "jitter_ms": "FLOAT",
                "packet_loss_pct": "FLOAT",
                "tcp_connect_avg_ms": "FLOAT",
                "throughput_mbps": "FLOAT",
                "quality": "INTEGER",
            },
            "metric_samples": {"source": "VARCHAR DEFAULT 'scan' NOT NULL"},
        }
        try:
            inspector = inspect(self.engine)
            existing = {table: {c["name"] for c in inspector.get_columns(table)} for table in new_columns}
        except Exception:
            return
        with self.engine.begin() as conn:
            for table, columns in new_columns.items():
                for name, sqltype in columns.items():
                    if name not in existing[table]:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sqltype}"))
            # Indexes added after a table already existed (create_all skips them).
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_uptime_mac_start "
                    "ON uptime_buckets (device_mac, bucket_start, probes, up)"
                )
            )

    def _setup_sqlite_pragmas(self) -> None:
        """WAL mode + busy timeout: the API and scheduler hit the DB concurrently."""

        @event.listens_for(self.engine, "connect")
        def _set_pragmas(dbapi_conn, _record) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    def record_scan(
        self,
        result: ScanResult,
        alert_on_new: bool = True,
        alert_on_down: bool = False,
        alert_on_ports: bool = True,
    ) -> list[AlertRecord]:
        """Persist a scan, diff against the inventory, return new alerts.

        Online/offline is always tracked (it used to be updated only when
        ``alert_on_down`` was set, so with the default config a device never
        went offline). ``alert_on_down`` now only decides whether down/back
        transitions also raise alerts. Only devices whose IP lies in the
        scanned network can be marked offline — a scan of another subnet no
        longer "downs" the rest of the inventory.
        """
        alerts: list[AlertRecord] = []
        events: list[DeviceEvent] = []
        now = datetime.now()
        scope = set(result.ports_scanned)

        def add_event(mac: str, kind: str, detail: str, **data: object) -> None:
            events.append(
                DeviceEvent(
                    created_at=now, device_mac=mac, kind=kind, detail=detail, data_json=json.dumps(data)
                )
            )

        with self._write_lock, Session(self.engine) as session:
            known = {d.mac: d for d in session.exec(select(DeviceRecord)).all()}
            seen_macs: set[str] = set()

            for dev in result.devices:
                if not dev.mac:
                    continue
                seen_macs.add(dev.mac)
                record = known.get(dev.mac)
                is_new = record is None
                if record is None:
                    record = DeviceRecord(mac=dev.mac, ip=dev.ip, first_seen=now)
                    session.add(record)
                    dev.is_new = True
                    dev.first_seen = now
                    add_event(dev.mac, "new", f"first seen at {dev.ip}", ip=dev.ip, vendor=dev.vendor)
                    if alert_on_new:
                        alerts.append(
                            AlertRecord(
                                kind="new_device",
                                device_mac=dev.mac,
                                device_ip=dev.ip,
                                detail=f"New device: {dev.ip} ({dev.vendor or dev.mdns_name or 'unknown'})",
                            )
                        )
                else:
                    if record.ip != dev.ip:
                        alerts.append(
                            AlertRecord(
                                kind="mac_changed",
                                device_mac=dev.mac,
                                device_ip=dev.ip,
                                detail=f"IP of {dev.mac} changed {record.ip} → {dev.ip}",
                            )
                        )
                        add_event(dev.mac, "ip_changed", f"{record.ip} → {dev.ip}", old=record.ip, new=dev.ip)
                        record.ip = dev.ip
                    if not record.online:
                        add_event(dev.mac, "up", "seen again by a scan", source="scan")
                        if alert_on_down:
                            alerts.append(
                                AlertRecord(
                                    kind="device_back",
                                    device_mac=dev.mac,
                                    device_ip=dev.ip,
                                    detail=f"Device back: {dev.ip} ({record.hostname or record.vendor or dev.mac})",
                                )
                            )

                record.last_seen = now
                record.online = True
                record.last_latency_ms = dev.latency_ms
                if record.last_latency_ms is None and dev.metrics is not None:
                    record.last_latency_ms = dev.metrics.latency_avg_ms
                self._merge_ports(record, dev, scope, is_new, alert_on_ports, alerts, add_event)
                for attr in ("hostname", "vendor", "mdns_name", "os_guess"):
                    value = getattr(dev, attr, "")
                    if value:
                        setattr(record, attr, value)
                # Persist the latest speed / quality metrics + a time-series sample.
                if dev.metrics is not None:
                    m = dev.metrics
                    record.jitter_ms = m.jitter_ms
                    record.packet_loss_pct = m.packet_loss_pct
                    record.tcp_connect_avg_ms = m.tcp_connect_avg_ms
                    record.throughput_mbps = m.throughput_mbps
                    record.quality = m.quality
                    session.add(
                        MetricSample(
                            created_at=now,
                            device_mac=dev.mac,
                            latency_ms=m.latency_avg_ms,
                            jitter_ms=m.jitter_ms,
                            packet_loss_pct=m.packet_loss_pct,
                            tcp_connect_avg_ms=m.tcp_connect_avg_ms,
                            throughput_mbps=m.throughput_mbps,
                            quality=m.quality,
                            online=True,
                            source="scan",
                        )
                    )
                if dev.conflict_macs:
                    self._conflict_alert(session, dev, alerts, add_event)
                dev.last_seen = now
                if dev.first_seen is None:
                    dev.first_seen = record.first_seen

            for mac, record in known.items():
                if mac in seen_macs or not record.online or not _in_network(record.ip, result.network):
                    continue
                record.online = False
                add_event(mac, "down", "not found by the scan", source="scan")
                if alert_on_down:
                    alerts.append(
                        AlertRecord(
                            kind="device_down",
                            device_mac=mac,
                            device_ip=record.ip,
                            detail=f"Device down: {record.ip} ({record.hostname or record.vendor or mac})",
                        )
                    )

            if result.gateway_ip and result.gateway_mac:
                self._check_gateway(session, result, now, alerts, add_event)

            for alert in alerts:
                session.add(alert)
            for ev in events:
                session.add(ev)
            session.add(
                ScanRecord(
                    duration_s=result.duration_s,
                    network=result.network,
                    total_devices=result.total_devices,
                    result_json=result.model_dump_json(),
                )
            )
            session.commit()
            self._prune_scans(session)
            self._prune_samples(session)
            for alert in alerts:
                session.refresh(alert)
        for alert in alerts:
            emit("alert", f"{alert.kind}: {alert.detail}", "warning", kind=alert.kind, ip=alert.device_ip)
        return alerts

    @staticmethod
    def _merge_ports(
        record: DeviceRecord,
        dev: Device,
        scope: set[int],
        is_new: bool,
        alert_on_ports: bool,
        alerts: list[AlertRecord],
        add_event: AddEvent,
    ) -> None:
        """Update the stored open ports from this pass, raising ports_changed.

        Ports outside this pass's probed set are kept (a quick scan after a
        full one must not forget the extended ports), so a port only counts
        as *closed* if it was probed. A host that answered nothing at all
        this time (no ICMP reply, no open port) is not diffed: that is a
        transient miss, not a reconfiguration. Before, an empty result never
        overwrote the stored list, so closed ports stayed in the inventory
        forever.
        """
        new_ports = {p.port: p.model_dump() for p in dev.open_ports}
        if not scope:
            # Legacy / single-stage pass with no port stage: only overwrite if
            # it found something (keeps what a previous full scan found).
            if dev.open_ports:
                record.open_ports_json = json.dumps(list(new_ports.values()), ensure_ascii=False)
            return
        try:
            old_ports = {
                int(p["port"]): p for p in json.loads(record.open_ports_json or "[]") if p.get("port")
            }
        except (ValueError, TypeError, KeyError, AttributeError):
            old_ports = {}
        responsive = bool(new_ports) or dev.latency_ms is not None
        if responsive:
            merged = {**{k: v for k, v in old_ports.items() if k not in scope}, **new_ports}
            closed = sorted(k for k in old_ports if k in scope and k not in new_ports)
        else:
            merged = {**old_ports, **new_ports}
            closed = []
        opened = sorted(set(new_ports) - set(old_ports))
        if not is_new and (opened or closed):
            parts = []
            if opened:
                parts.append("opened " + ", ".join(f"{p}/{new_ports[p].get('service', '?')}" for p in opened))
            if closed:
                parts.append("closed " + ", ".join(str(p) for p in closed))
            detail = f"{dev.ip}: " + "; ".join(parts)
            add_event(dev.mac, "ports_changed", detail, opened=opened, closed=closed)
            if alert_on_ports:
                alerts.append(
                    AlertRecord(kind="ports_changed", device_mac=dev.mac, device_ip=dev.ip, detail=detail)
                )
        record.open_ports_json = json.dumps(
            sorted(merged.values(), key=lambda p: p["port"]), ensure_ascii=False
        )

    @staticmethod
    def _conflict_alert(
        session: Session, dev: Device, alerts: list[AlertRecord], add_event: AddEvent
    ) -> None:
        key = f"conflict:{dev.ip}"
        value = ",".join(sorted({dev.mac, *dev.conflict_macs}))
        previous = session.get(MetaRecord, key)
        if previous is not None and previous.value == value:
            return  # this exact conflict was already reported
        detail = f"IP conflict on {dev.ip}: answered by {value.replace(',', ', ')}"
        alerts.append(AlertRecord(kind="ip_conflict", device_mac=dev.mac, device_ip=dev.ip, detail=detail))
        add_event(dev.mac, "conflict", detail, macs=value.split(","))
        if previous is None:
            session.add(MetaRecord(key=key, value=value))
        else:
            previous.value = value
            session.add(previous)

    @staticmethod
    def _check_gateway(
        session: Session, result: ScanResult, now: datetime, alerts: list[AlertRecord], add_event: AddEvent
    ) -> None:
        """The gateway's MAC changing is the classic ARP-spoofing (MITM) tell."""
        key = f"gateway_mac:{result.gateway_ip}"
        previous = session.get(MetaRecord, key)
        if previous is not None and previous.value and previous.value != result.gateway_mac:
            detail = (
                f"Gateway {result.gateway_ip} now answers from {result.gateway_mac} "
                f"(was {previous.value}) — router replaced, or ARP spoofing / MITM"
            )
            alerts.append(
                AlertRecord(
                    kind="gateway_mac_changed",
                    device_mac=result.gateway_mac,
                    device_ip=result.gateway_ip,
                    detail=detail,
                )
            )
            add_event(result.gateway_mac, "gateway_mac_changed", detail, old=previous.value)
            emit("security", detail, "error")
        if previous is None:
            session.add(MetaRecord(key=key, value=result.gateway_mac))
        else:
            previous.value = result.gateway_mac
            previous.updated_at = now
            session.add(previous)

    @staticmethod
    def _prune_samples(session: Session, keep: int = METRIC_RETENTION) -> None:
        """Keep only the newest ``keep`` metric samples per device."""
        macs = session.exec(select(MetricSample.device_mac).distinct()).all()
        for mac in macs:
            ids = session.exec(
                select(MetricSample.id)
                .where(MetricSample.device_mac == mac)
                .order_by(MetricSample.created_at.desc())  # type: ignore[attr-defined]
            ).all()
            for sample_id in ids[keep:]:
                obj = session.get(MetricSample, sample_id)
                if obj is not None:
                    session.delete(obj)
        session.commit()

    @staticmethod
    def _prune_scans(session: Session, keep: int = SCAN_RETENTION) -> None:
        """Drop the oldest scans beyond ``keep`` so the DB does not grow forever."""
        ids = session.exec(
            select(ScanRecord.id).order_by(ScanRecord.started_at.desc())  # type: ignore[attr-defined]
        ).all()
        stale = ids[keep:]
        if not stale:
            return
        for scan_id in stale:
            record = session.get(ScanRecord, scan_id)
            if record is not None:
                session.delete(record)
        session.commit()

    def list_devices(self) -> list[DeviceRecord]:
        with Session(self.engine) as session:
            return list(session.exec(select(DeviceRecord).order_by(DeviceRecord.ip)).all())

    def list_alerts(self, unacknowledged_only: bool = False) -> list[AlertRecord]:
        with Session(self.engine) as session:
            stmt = select(AlertRecord).order_by(AlertRecord.created_at.desc())  # type: ignore[attr-defined]
            if unacknowledged_only:
                stmt = stmt.where(AlertRecord.acknowledged.is_(False))  # type: ignore[attr-defined]
            return list(session.exec(stmt).all())

    def add_alerts(self, alerts: list[AlertRecord]) -> list[AlertRecord]:
        """Persist alerts raised outside a scan (live monitor, cert watch)."""
        if not alerts:
            return []
        with self._write_lock, Session(self.engine) as session:
            for alert in alerts:
                session.add(alert)
            session.commit()
            for alert in alerts:
                session.refresh(alert)
        for alert in alerts:
            emit("alert", f"{alert.kind}: {alert.detail}", "warning", kind=alert.kind, ip=alert.device_ip)
        return alerts

    def acknowledge_alert(self, alert_id: int) -> bool:
        with Session(self.engine) as session:
            alert = session.get(AlertRecord, alert_id)
            if not alert:
                return False
            alert.acknowledged = True
            session.add(alert)
            session.commit()
            return True

    def acknowledge_all_alerts(self) -> int:
        with Session(self.engine) as session:
            pending = session.exec(select(AlertRecord).where(AlertRecord.acknowledged.is_(False))).all()  # type: ignore[attr-defined]
            for alert in pending:
                alert.acknowledged = True
                session.add(alert)
            session.commit()
            return len(pending)

    def set_device_trusted(self, mac: str, trusted: bool, notes: str | None = None) -> bool:
        with Session(self.engine) as session:
            record = session.exec(select(DeviceRecord).where(DeviceRecord.mac == mac)).first()
            if not record:
                return False
            if record.trusted != trusted:
                session.add(
                    DeviceEvent(
                        device_mac=mac,
                        kind="trusted" if trusted else "untrusted",
                        detail="changed from the dashboard",
                    )
                )
            record.trusted = trusted
            if notes is not None:
                record.notes = notes
            session.add(record)
            session.commit()
            return True

    def last_scan(self) -> ScanRecord | None:
        with Session(self.engine) as session:
            return session.exec(
                select(ScanRecord).order_by(ScanRecord.started_at.desc())  # type: ignore[attr-defined]
            ).first()

    def metric_samples(self, mac: str, limit: int = 100) -> list[MetricSample]:
        """Newest-first metric samples for one device (oldest last)."""
        with Session(self.engine) as session:
            rows = session.exec(
                select(MetricSample)
                .where(MetricSample.device_mac == mac)
                .order_by(MetricSample.created_at.desc())  # type: ignore[attr-defined]
                .limit(limit)
            ).all()
            return list(reversed(rows))

    def metrics_summary(self) -> dict[str, object]:
        """Aggregate quality metrics across the current inventory."""
        with Session(self.engine) as session:
            devices = list(session.exec(select(DeviceRecord)).all())
        online = [d for d in devices if d.online]
        latencies = [d.last_latency_ms for d in online if d.last_latency_ms is not None]
        qualities = [d.quality for d in online if d.quality is not None]
        losses = [d.packet_loss_pct for d in online if d.packet_loss_pct is not None]
        throughputs = [d.throughput_mbps for d in online if d.throughput_mbps is not None]

        def _avg(values: list[float]) -> float | None:
            return round(sum(values) / len(values), 2) if values else None

        def _p95(values: list[float]) -> float | None:
            if not values:
                return None
            ordered = sorted(values)
            return round(ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))], 2)

        return {
            "devices_total": len(devices),
            "devices_online": len(online),
            "avg_latency_ms": _avg(latencies),
            "p95_latency_ms": _p95(latencies),
            "avg_quality": round(sum(qualities) / len(qualities)) if qualities else None,
            "avg_packet_loss_pct": _avg(losses),
            "max_throughput_mbps": max(throughputs) if throughputs else None,
            "worst_quality": min(qualities) if qualities else None,
            "devices_measured": len(qualities),
        }

    def metrics_history(self, limit: int = 200) -> list[dict[str, object]]:
        """Network-wide metric averages per scan, over time.

        Every device measured in one scan shares a single ``created_at`` (see
        ``record_scan``), so grouping samples by that timestamp reconstructs a
        per-scan network trend. On-demand speed tests (source "speedtest")
        are excluded — a single device is not a network average.
        Chronological (oldest first), newest ``limit``.
        """
        with Session(self.engine) as session:
            rows = list(
                session.exec(
                    select(MetricSample)
                    .where(MetricSample.source == "scan")
                    .order_by(MetricSample.created_at.asc())  # type: ignore[attr-defined]
                ).all()
            )
        buckets: dict[datetime, list[MetricSample]] = {}
        order: list[datetime] = []
        for sample in rows:
            if sample.created_at not in buckets:
                buckets[sample.created_at] = []
                order.append(sample.created_at)
            buckets[sample.created_at].append(sample)

        def _avg(values: list[float | None]) -> float | None:
            nums = [v for v in values if v is not None]
            return round(sum(nums) / len(nums), 2) if nums else None

        def _avg_int(values: list[int | None]) -> int | None:
            nums = [v for v in values if v is not None]
            return round(sum(nums) / len(nums)) if nums else None

        points: list[dict[str, object]] = []
        for ts in order:
            samples = buckets[ts]
            points.append(
                {
                    "t": iso(ts),
                    "avg_latency_ms": _avg([sm.latency_ms for sm in samples]),
                    "avg_quality": _avg_int([sm.quality for sm in samples]),
                    "avg_packet_loss_pct": _avg([sm.packet_loss_pct for sm in samples]),
                    "avg_throughput_mbps": _avg([sm.throughput_mbps for sm in samples]),
                    # Devices measured in that scan (with ≥1 echo answered
                    # → responding; the rest were found at L2 only).
                    "devices": len(samples),
                    "devices_responding": sum(1 for sm in samples if sm.latency_ms is not None),
                }
            )
        return points[-limit:]

    def scan_history(self, limit: int = 100) -> list[dict[str, object]]:
        """Metadata of recent scans over time (chronological, newest ``limit``)."""
        with Session(self.engine) as session:
            rows = list(
                session.exec(
                    select(ScanRecord).order_by(ScanRecord.started_at.asc())  # type: ignore[attr-defined]
                ).all()
            )
        return [
            {
                "started_at": iso(r.started_at),
                "duration_s": r.duration_s,
                "total_devices": r.total_devices,
                "network": r.network,
            }
            for r in rows[-limit:]
        ]

    def record_speedtest(self, mac: str, metrics) -> bool:  # metrics: DeviceMetrics
        """Persist an on-demand speed test result for a single device."""
        with Session(self.engine) as session:
            record = session.exec(select(DeviceRecord).where(DeviceRecord.mac == mac)).first()
            if not record:
                return False
            record.last_latency_ms = metrics.latency_avg_ms
            record.jitter_ms = metrics.jitter_ms
            record.packet_loss_pct = metrics.packet_loss_pct
            record.tcp_connect_avg_ms = metrics.tcp_connect_avg_ms
            record.throughput_mbps = metrics.throughput_mbps
            record.quality = metrics.quality
            session.add(record)
            session.add(
                MetricSample(
                    device_mac=mac,
                    latency_ms=metrics.latency_avg_ms,
                    jitter_ms=metrics.jitter_ms,
                    packet_loss_pct=metrics.packet_loss_pct,
                    tcp_connect_avg_ms=metrics.tcp_connect_avg_ms,
                    throughput_mbps=metrics.throughput_mbps,
                    quality=metrics.quality,
                    online=True,
                    source="speedtest",
                )
            )
            session.commit()
            return True

    def device_by_mac(self, mac: str) -> DeviceRecord | None:
        with Session(self.engine) as session:
            return session.exec(select(DeviceRecord).where(DeviceRecord.mac == mac)).first()

    def set_device_notes(self, mac: str, notes: str) -> bool:
        with Session(self.engine) as session:
            record = session.exec(select(DeviceRecord).where(DeviceRecord.mac == mac)).first()
            if not record:
                return False
            record.notes = notes
            session.add(record)
            session.commit()
            return True

    # -- Live monitor: state, uptime buckets, timeline -------------------------

    def set_device_state(
        self, mac: str, online: bool, when: datetime, detail: str = "", **data: object
    ) -> None:
        """Record an up/down transition decided by the live monitor."""
        with self._write_lock, Session(self.engine) as session:
            record = session.exec(select(DeviceRecord).where(DeviceRecord.mac == mac)).first()
            if record is None:
                return
            record.online = online
            if online:
                record.last_seen = when
            session.add(record)
            session.add(
                DeviceEvent(
                    created_at=when,
                    device_mac=mac,
                    kind="up" if online else "down",
                    detail=detail,
                    data_json=json.dumps(data),
                )
            )
            session.commit()

    def touch_devices(self, macs: list[str], when: datetime) -> None:
        """Bump last_seen for devices that answered a live probe."""
        if not macs:
            return
        with self._write_lock, Session(self.engine) as session:
            stmt = select(DeviceRecord).where(DeviceRecord.mac.in_(macs))  # type: ignore[attr-defined]
            for record in session.exec(stmt).all():
                record.last_seen = when
                session.add(record)
            session.commit()

    def add_uptime(self, rows: list[dict[str, object]]) -> None:
        """Merge probe counters into their (mac, bucket_start) rows."""
        if not rows:
            return
        with self._write_lock, Session(self.engine) as session:
            for row in rows:
                mac = str(row["mac"])
                start = row["bucket_start"]
                assert isinstance(start, datetime)
                bucket = session.exec(
                    select(UptimeBucket).where(
                        UptimeBucket.device_mac == mac, UptimeBucket.bucket_start == start
                    )
                ).first()
                if bucket is None:
                    bucket = UptimeBucket(device_mac=mac, bucket_start=start)
                bucket.probes += int(row["probes"])  # type: ignore[call-overload]
                bucket.up += int(row["up"])  # type: ignore[call-overload]
                bucket.rtt_sum_ms += float(row["rtt_sum_ms"])  # type: ignore[arg-type]
                bucket.rtt_count += int(row.get("rtt_count", 0))  # type: ignore[call-overload]
                for attr, pick in (("rtt_min_ms", min), ("rtt_max_ms", max)):
                    value = row.get(attr)
                    if value is not None:
                        current = getattr(bucket, attr)
                        setattr(bucket, attr, value if current is None else pick(current, value))
                session.add(bucket)
            session.commit()

    def uptime_sums(self, since: datetime, mac: str | None = None) -> dict[str, tuple[int, int]]:
        """(probes, up) per device since ``since``, aggregated in SQL."""
        bucket = UptimeBucket.__table__.c  # type: ignore[attr-defined]
        stmt = sa_select(bucket.device_mac, func.sum(bucket.probes), func.sum(bucket.up)).where(
            bucket.bucket_start >= since
        )
        if mac:
            stmt = stmt.where(bucket.device_mac == mac)
        with Session(self.engine) as session:
            rows = session.execute(stmt.group_by(bucket.device_mac)).all()
        return {str(m): (int(p or 0), int(u or 0)) for m, p, u in rows}

    def uptime_rows(self, since: datetime, mac: str | None = None) -> list[tuple]:
        """Raw bucket tuples (mac, start, probes, up, rtt_sum, rtt_count,
        rtt_min, rtt_max) since ``since`` — plain tuples, not ORM objects:
        building 200k model instances was most of the uptime report's cost."""
        bucket = UptimeBucket.__table__.c  # type: ignore[attr-defined]
        stmt = sa_select(
            bucket.device_mac,
            bucket.bucket_start,
            bucket.probes,
            bucket.up,
            bucket.rtt_sum_ms,
            bucket.rtt_count,
            bucket.rtt_min_ms,
            bucket.rtt_max_ms,
        ).where(bucket.bucket_start >= since)
        if mac:
            stmt = stmt.where(bucket.device_mac == mac)
        with Session(self.engine) as session:
            return [tuple(r) for r in session.execute(stmt).all()]

    def uptime_buckets(self, since: datetime, mac: str | None = None) -> list[UptimeBucket]:
        with Session(self.engine) as session:
            stmt = select(UptimeBucket).where(UptimeBucket.bucket_start >= since)
            if mac:
                stmt = stmt.where(UptimeBucket.device_mac == mac)
            return list(session.exec(stmt.order_by(UptimeBucket.bucket_start.asc())).all())  # type: ignore[attr-defined]

    def device_events(
        self,
        mac: str | None = None,
        since: datetime | None = None,
        kinds: set[str] | None = None,
        limit: int = 500,
    ) -> list[DeviceEvent]:
        """Timeline events, newest first."""
        with Session(self.engine) as session:
            stmt = select(DeviceEvent)
            if mac:
                stmt = stmt.where(DeviceEvent.device_mac == mac)
            if since:
                stmt = stmt.where(DeviceEvent.created_at >= since)
            if kinds:
                stmt = stmt.where(DeviceEvent.kind.in_(kinds))  # type: ignore[attr-defined]
            stmt = stmt.order_by(DeviceEvent.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
            return list(session.exec(stmt).all())

    def prune_live(self, now: datetime | None = None) -> None:
        now = now or datetime.now()
        with self._write_lock, Session(self.engine) as session:
            session.exec(delete(UptimeBucket).where(UptimeBucket.bucket_start < now - UPTIME_RETENTION))  # type: ignore[arg-type]
            session.exec(delete(DeviceEvent).where(DeviceEvent.created_at < now - EVENT_RETENTION))  # type: ignore[arg-type]
            session.commit()

    def get_meta(self, key: str) -> str | None:
        with Session(self.engine) as session:
            row = session.get(MetaRecord, key)
            return row.value if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._write_lock, Session(self.engine) as session:
            row = session.get(MetaRecord, key)
            if row is None:
                row = MetaRecord(key=key, value=value)
            row.value = value
            row.updated_at = datetime.now()
            session.add(row)
            session.commit()

    # -- Dashboard-managed integrations (Proxmox/TrueNAS/AdGuard/Pi-hole/custom) --

    def list_integrations(self, kind: str | None = None) -> list[IntegrationInstance]:
        with Session(self.engine) as session:
            stmt = select(IntegrationInstance).order_by(IntegrationInstance.created_at.desc())  # type: ignore[attr-defined]
            if kind:
                stmt = stmt.where(IntegrationInstance.kind == kind)
            return list(session.exec(stmt).all())

    def get_integration(self, integration_id: int) -> IntegrationInstance | None:
        with Session(self.engine) as session:
            return session.get(IntegrationInstance, integration_id)

    def create_integration(
        self, kind: str, name: str, config_json: str, enabled: bool = True, logo_path: str | None = None
    ) -> IntegrationInstance:
        with Session(self.engine) as session:
            record = IntegrationInstance(
                kind=kind, name=name, config_json=config_json, enabled=enabled, logo_path=logo_path
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def update_integration(
        self,
        integration_id: int,
        name: str | None = None,
        config_json: str | None = None,
        enabled: bool | None = None,
        logo_path: str | None = None,
    ) -> IntegrationInstance | None:
        with Session(self.engine) as session:
            record = session.get(IntegrationInstance, integration_id)
            if not record:
                return None
            if name is not None:
                record.name = name
            if config_json is not None:
                record.config_json = config_json
            if enabled is not None:
                record.enabled = enabled
            if logo_path is not None:
                record.logo_path = logo_path
            record.updated_at = datetime.now()
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def delete_integration(self, integration_id: int) -> bool:
        with Session(self.engine) as session:
            record = session.get(IntegrationInstance, integration_id)
            if not record:
                return False
            session.delete(record)
            session.commit()
            return True
