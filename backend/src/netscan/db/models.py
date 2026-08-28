"""SQLModel tables for the persistent inventory.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel


class DeviceRecord(SQLModel, table=True):
    """One known device in the inventory (keyed by MAC when available)."""

    __tablename__ = "devices"

    id: int | None = Field(default=None, primary_key=True)
    mac: str = Field(index=True)
    ip: str = Field(index=True)
    hostname: str = ""
    vendor: str = ""
    mdns_name: str = ""
    os_guess: str = ""
    notes: str = ""
    trusted: bool = False  # user-acknowledged device
    first_seen: datetime = Field(default_factory=datetime.now)
    last_seen: datetime = Field(default_factory=datetime.now)
    last_latency_ms: float | None = None
    open_ports_json: str = "[]"
    online: bool = True
    # Latest speed / quality metrics (see scanner.speed)
    jitter_ms: float | None = None
    packet_loss_pct: float | None = None
    tcp_connect_avg_ms: float | None = None
    throughput_mbps: float | None = None
    quality: int | None = None


class MetricSample(SQLModel, table=True):
    """Time-series sample of a device's metrics, one row per scan per device."""

    __tablename__ = "metric_samples"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    device_mac: str = Field(index=True)
    latency_ms: float | None = None
    jitter_ms: float | None = None
    packet_loss_pct: float | None = None
    tcp_connect_avg_ms: float | None = None
    throughput_mbps: float | None = None
    quality: int | None = None
    online: bool = True


class ScanRecord(SQLModel, table=True):
    """Metadata of one completed scan."""

    __tablename__ = "scans"

    id: int | None = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=datetime.now)
    duration_s: float = 0.0
    network: str = ""
    total_devices: int = 0
    result_json: str = "{}"


class AlertRecord(SQLModel, table=True):
    """One alert raised by the inventory diff."""

    __tablename__ = "alerts"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    kind: str  # new_device | mac_changed | device_down | device_back
    device_mac: str = ""
    device_ip: str = ""
    detail: str = ""
    acknowledged: bool = False
