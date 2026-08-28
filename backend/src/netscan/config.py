"""NetScan configuration.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Configuration is resolved in this order (later wins):
  1. Defaults
  2. YAML config file (``netscan.yaml``, path via ``NETSCAN_CONFIG``)
  3. Environment variables prefixed with ``NETSCAN_``

Secrets (API tokens, passwords) should always come from environment
variables, never be committed to the YAML file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProxmoxInstance(BaseModel):
    """One Proxmox VE node or cluster endpoint."""

    name: str
    host: str
    port: int = 8006
    # API token in the form "user@realm!tokenid" + secret (env recommended)
    token_id: str = ""
    token_secret: str = ""
    verify_ssl: bool = False
    enabled: bool = True


class TrueNASInstance(BaseModel):
    """One TrueNAS (CORE or SCALE) endpoint."""

    name: str
    host: str
    port: int = 443
    use_ssl: bool = True
    api_key: str = ""
    verify_ssl: bool = False
    enabled: bool = True


class AdGuardInstance(BaseModel):
    """One AdGuard Home endpoint."""

    name: str
    host: str
    port: int = 80
    username: str = ""
    password: str = ""
    use_ssl: bool = False
    verify_ssl: bool = False
    enabled: bool = True


class ScanDefaults(BaseModel):
    network: str = ""  # empty = auto-detect
    workers: int = 16
    port_timeout: float = 0.5
    ping_timeout: float = 1.0
    interval_minutes: int = 60  # scheduled re-scan cadence (0 = disabled)
    full: bool = False
    use_mdns: bool = True
    use_fingerprint: bool = True
    use_nmap: bool = True  # only if binary is present
    use_nmap_os: bool = False  # nmap -O needs privileges and is slow
    use_rustscan: bool = True  # fast full-range discovery, only if installed
    use_nuclei: bool = False  # vulnerability scan of web UIs (opt-in)
    nuclei_max_targets: int = 20
    use_whatweb: bool = False  # web technology fingerprint of discovered web UIs (opt-in)
    whatweb_max_targets: int = 20
    use_testssl: bool = False  # TLS configuration audit of discovered HTTPS UIs (opt-in, slow)
    testssl_max_targets: int = 10
    alert_on_new_device: bool = True
    alert_on_device_down: bool = False
    # Speed / quality metrics
    use_speedtest: bool = True  # latency stats + TCP handshake per device
    speedtest_pings: int = 5  # ICMP echoes per device for jitter/loss
    use_throughput: bool = False  # HTTP download throughput estimate (heavier)


class Settings(BaseSettings):
    """Runtime settings for the NetScan backend."""

    model_config = SettingsConfigDict(env_prefix="NETSCAN_", env_nested_delimiter="__")

    data_dir: Path = Field(default=Path("data"))
    database_url: str = ""  # empty = sqlite under data_dir
    api_host: str = "127.0.0.1"  # localhost by default; 0.0.0.0 requires api_token
    api_port: int = 8600
    # Empty = no auth (only safe on localhost). Set NETSCAN_API_TOKEN when
    # exposing the API beyond this machine.
    api_token: str = ""
    api_cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    scan: ScanDefaults = Field(default_factory=ScanDefaults)
    proxmox: list[ProxmoxInstance] = Field(default_factory=list)
    truenas: list[TrueNASInstance] = Field(default_factory=list)
    adguard: list[AdGuardInstance] = Field(default_factory=list)

    # Apprise notification URLs (ntfy://, tgram://, discord://, ...)
    notify_urls: list[str] = Field(default_factory=list)

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'netscan.db'}"


def load_settings(config_path: str | os.PathLike[str] | None = None) -> Settings:
    """Load settings from YAML file + environment."""
    path = Path(config_path or os.environ.get("NETSCAN_CONFIG", "netscan.yaml"))
    file_data: dict[str, Any] = {}
    if path.is_file():
        with open(path, encoding="utf-8") as fh:
            file_data = yaml.safe_load(fh) or {}
    return Settings(**file_data)
