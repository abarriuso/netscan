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
    enabled: bool = True


class ScanDefaults(BaseModel):
    network: str = ""  # empty = auto-detect
    workers: int = 50
    port_timeout: float = 0.5
    ping_timeout: float = 1.0
    interval_minutes: int = 60  # scheduled re-scan cadence (0 = disabled)
    full: bool = False
    use_mdns: bool = True
    use_fingerprint: bool = True
    use_nmap: bool = True  # only if binary is present
    alert_on_new_device: bool = True
    alert_on_device_down: bool = False


class Settings(BaseSettings):
    """Runtime settings for the NetScan backend."""

    model_config = SettingsConfigDict(env_prefix="NETSCAN_", env_nested_delimiter="__")

    data_dir: Path = Field(default=Path("data"))
    database_url: str = ""  # empty = sqlite under data_dir
    api_host: str = "0.0.0.0"
    api_port: int = 8600
    api_cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

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
