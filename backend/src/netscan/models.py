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
    # Inventory state, filled by the persistence layer
    is_new: bool = False
    first_seen: datetime | None = None
    last_seen: datetime | None = None


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
