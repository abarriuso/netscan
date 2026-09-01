"""Inventory store: persists scans, diffs devices, raises alerts.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import event, inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from netscan.db.models import AlertRecord, DeviceRecord, IntegrationInstance, MetricSample, ScanRecord
from netscan.models import ScanResult

# How many historical scans to keep in the DB (oldest are pruned).
SCAN_RETENTION = 200
# How many metric samples to keep per device (oldest pruned).
METRIC_RETENTION = 500


class InventoryStore:
    def __init__(self, db_url: str, data_dir: str | None = None) -> None:
        if data_dir:
            from pathlib import Path

            Path(data_dir).mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(db_url, echo=False)
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
            "jitter_ms": "FLOAT",
            "packet_loss_pct": "FLOAT",
            "tcp_connect_avg_ms": "FLOAT",
            "throughput_mbps": "FLOAT",
            "quality": "INTEGER",
        }
        try:
            inspector = inspect(self.engine)
            existing = {c["name"] for c in inspector.get_columns("devices")}
        except Exception:
            return
        missing = {k: v for k, v in new_columns.items() if k not in existing}
        if not missing:
            return
        with self.engine.begin() as conn:
            for name, sqltype in missing.items():
                conn.execute(text(f"ALTER TABLE devices ADD COLUMN {name} {sqltype}"))

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
    ) -> list[AlertRecord]:
        """Persist a scan, diff against the inventory, return new alerts."""
        alerts: list[AlertRecord] = []
        now = datetime.now()

        with Session(self.engine) as session:
            known = {d.mac: d for d in session.exec(select(DeviceRecord)).all()}
            seen_macs: set[str] = set()

            for dev in result.devices:
                if not dev.mac:
                    continue
                seen_macs.add(dev.mac)
                record = known.get(dev.mac)
                if record is None:
                    record = DeviceRecord(mac=dev.mac, ip=dev.ip, first_seen=now)
                    session.add(record)
                    dev.is_new = True
                    dev.first_seen = now
                    if alert_on_new:
                        alerts.append(
                            AlertRecord(
                                kind="new_device",
                                device_mac=dev.mac,
                                device_ip=dev.ip,
                                detail=f"Nuevo dispositivo: {dev.ip} "
                                f"({dev.vendor or dev.mdns_name or 'desconocido'})",
                            )
                        )
                elif record.ip != dev.ip:
                    alerts.append(
                        AlertRecord(
                            kind="mac_changed",
                            device_mac=dev.mac,
                            device_ip=dev.ip,
                            detail=f"IP de {dev.mac} cambió {record.ip} → {dev.ip}",
                        )
                    )
                    record.ip = dev.ip

                record.last_seen = now
                record.online = True
                record.last_latency_ms = dev.latency_ms
                if record.last_latency_ms is None and dev.metrics is not None:
                    record.last_latency_ms = dev.metrics.latency_avg_ms
                if dev.open_ports:
                    # Only overwrite when this pass actually scanned ports: a
                    # single-tool run (mDNS-only, ARP-only...) reports no
                    # ports at all and must not wipe out what a previous
                    # full scan already found — same "don't clobber with an
                    # empty result" rule already applied to hostname/vendor.
                    record.open_ports_json = json.dumps(
                        [p.model_dump() for p in dev.open_ports], ensure_ascii=False
                    )
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
                        )
                    )
                dev.last_seen = now
                if dev.first_seen is None:
                    dev.first_seen = record.first_seen

            if alert_on_down:
                for mac, record in known.items():
                    if mac not in seen_macs and record.online:
                        record.online = False
                        alerts.append(
                            AlertRecord(
                                kind="device_down",
                                device_mac=mac,
                                device_ip=record.ip,
                                detail=f"Dispositivo caído: {record.ip} "
                                f"({record.hostname or record.vendor or mac})",
                            )
                        )

            for alert in alerts:
                session.add(alert)
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
        return alerts

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

    def acknowledge_alert(self, alert_id: int) -> bool:
        with Session(self.engine) as session:
            alert = session.get(AlertRecord, alert_id)
            if not alert:
                return False
            alert.acknowledged = True
            session.add(alert)
            session.commit()
            return True

    def set_device_trusted(self, mac: str, trusted: bool, notes: str | None = None) -> bool:
        with Session(self.engine) as session:
            record = session.exec(select(DeviceRecord).where(DeviceRecord.mac == mac)).first()
            if not record:
                return False
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

        return {
            "devices_total": len(devices),
            "devices_online": len(online),
            "avg_latency_ms": _avg(latencies),
            "avg_quality": round(sum(qualities) / len(qualities)) if qualities else None,
            "avg_packet_loss_pct": _avg(losses),
            "max_throughput_mbps": max(throughputs) if throughputs else None,
            "worst_quality": min(qualities) if qualities else None,
        }

    def metrics_history(self, limit: int = 200) -> list[dict[str, object]]:
        """Network-wide metric averages per scan, over time.

        Every device measured in one scan shares a single ``created_at`` (see
        ``record_scan``), so grouping samples by that timestamp reconstructs a
        per-scan network trend. Chronological (oldest first), newest ``limit``.
        """
        with Session(self.engine) as session:
            rows = list(
                session.exec(
                    select(MetricSample).order_by(MetricSample.created_at.asc())  # type: ignore[attr-defined]
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
                    "t": ts.isoformat(),
                    "avg_latency_ms": _avg([sm.latency_ms for sm in samples]),
                    "avg_quality": _avg_int([sm.quality for sm in samples]),
                    "avg_packet_loss_pct": _avg([sm.packet_loss_pct for sm in samples]),
                    "avg_throughput_mbps": _avg([sm.throughput_mbps for sm in samples]),
                    "devices": len(samples),
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
                "started_at": r.started_at.isoformat(),
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
                )
            )
            session.commit()
            return True

    def device_by_mac(self, mac: str) -> DeviceRecord | None:
        with Session(self.engine) as session:
            return session.exec(select(DeviceRecord).where(DeviceRecord.mac == mac)).first()

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
