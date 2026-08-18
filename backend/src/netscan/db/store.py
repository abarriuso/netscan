"""Inventory store: persists scans, diffs devices, raises alerts.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine, select

from netscan.db.models import AlertRecord, DeviceRecord, ScanRecord
from netscan.models import ScanResult


class InventoryStore:
    def __init__(self, db_url: str, data_dir: str | None = None) -> None:
        if data_dir:
            from pathlib import Path

            Path(data_dir).mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(db_url, echo=False)
        SQLModel.metadata.create_all(self.engine)

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
                record.open_ports_json = json.dumps(
                    [p.model_dump() for p in dev.open_ports], ensure_ascii=False
                )
                for attr in ("hostname", "vendor", "mdns_name", "os_guess"):
                    value = getattr(dev, attr, "")
                    if value:
                        setattr(record, attr, value)
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
            for alert in alerts:
                session.refresh(alert)
        return alerts

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
