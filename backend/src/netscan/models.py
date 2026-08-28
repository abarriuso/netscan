"""Shared pydantic schemas for scan results.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PortInfo(BaseModel):
    port: int
    service: str = "unknown"
    version: str = ""  # filled by nmap -sV when available


class TlsInfo(BaseModel):
    issuer: str = ""
    subject: str = ""
    not_before: str = ""
    not_after: str = ""
    days_remaining: int | None = None
    self_signed: bool = False
    version: str = ""  # TLS protocol version negotiated


class HttpInfo(BaseModel):
    url: str
    status_code: int = 0
    title: str = ""
    server: str = ""
    tls: TlsInfo | None = None


class DeviceMetrics(BaseModel):
    """Link / service quality metrics for one device (see scanner.speed)."""

    latency_avg_ms: float | None = None
    latency_min_ms: float | None = None
    latency_max_ms: float | None = None
    jitter_ms: float | None = None
    packet_loss_pct: float | None = None
    # Per-port TCP handshake time in ms: {port: ms}
    tcp_connect_ms: dict[int, float] = Field(default_factory=dict)
    tcp_connect_avg_ms: float | None = None
    throughput_mbps: float | None = None
    throughput_port: int | None = None
    quality: int | None = None  # 0-100 composite score
    measured_at: datetime | None = None


class Device(BaseModel):
    ip: str
    mac: str = ""
    hostname: str = ""
    vendor: str = ""
    latency_ms: float | None = None
    os_guess: str = ""
    open_ports: list[PortInfo] = Field(default_factory=list)
    mdns_name: str = ""
    mdns_services: list[str] = Field(default_factory=list)
    http: list[HttpInfo] = Field(default_factory=list)
    metrics: DeviceMetrics | None = None
    # Inventory state, filled by the persistence layer
    is_new: bool = False
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class StageTiming(BaseModel):
    """Wall-clock duration of one scan stage, for the metrics view."""

    stage: str
    duration_s: float = 0.0


class ScanResult(BaseModel):
    scan_time: datetime = Field(default_factory=datetime.now)
    network: str = ""
    interface: str = ""
    local_ip: str = ""
    total_devices: int = 0
    duration_s: float = 0.0
    devices: list[Device] = Field(default_factory=list)
    vulnerabilities: list[dict[str, str]] = Field(default_factory=list)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    # Extended scan-wide metrics
    stage_timings: list[StageTiming] = Field(default_factory=list)
    ports_open_total: int = 0
    link_speed_mbps: int | None = None
    speedtest_ran: bool = False
