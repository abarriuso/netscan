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

import ipaddress
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_HOSTNAME_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?)*$"
)


def _check_host(value: str) -> str:
    """A bare hostname or IP: integration URLs are built as f"{scheme}://{host}:{port}/...",
    so "evil.example/x?" or "user@evil.example" would send the credential elsewhere."""
    value = value.strip()
    candidate = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    try:
        ipaddress.ip_address(candidate)
        return value
    except ValueError:
        pass
    if not _HOSTNAME_RE.fullmatch(value):
        raise ValueError("host must be a hostname or an IP address (no scheme, port or path)")
    return value


class _HostInstance(BaseModel):
    """Base for integrations reached at ``host``: validates it."""

    @field_validator("host", check_fields=False)
    @classmethod
    def _valid_host(cls, value: str) -> str:
        return _check_host(value)


class ProxmoxInstance(_HostInstance):
    """One Proxmox VE node or cluster endpoint."""

    name: str
    host: str
    port: int = 8006
    # API token in the form "user@realm!tokenid" + secret (env recommended)
    token_id: str = ""
    token_secret: str = ""
    verify_ssl: bool = False
    enabled: bool = True


class TrueNASInstance(_HostInstance):
    """One TrueNAS (CORE or SCALE) endpoint."""

    name: str
    host: str
    port: int = 443
    use_ssl: bool = True
    api_key: str = ""
    verify_ssl: bool = False
    enabled: bool = True


class AdGuardInstance(_HostInstance):
    """One AdGuard Home endpoint."""

    name: str
    host: str
    port: int = 80
    username: str = ""
    password: str = ""
    use_ssl: bool = False
    verify_ssl: bool = False
    enabled: bool = True


class PiholeInstance(_HostInstance):
    """One Pi-hole endpoint (API v6 only — v5 is end-of-life)."""

    name: str
    host: str
    port: int = 80
    password: str = ""  # the Pi-hole admin password / app password
    use_ssl: bool = False
    verify_ssl: bool = False
    enabled: bool = True


class CustomInstance(BaseModel):
    """A monitored bookmark tile for any other service — name, URL, and an
    optional uploaded logo (logo_path lives on IntegrationInstance itself,
    not here, since it's a file on disk rather than connection config)."""

    name: str
    url: str
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        value = value.strip()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("url must be an http:// or https:// address")
        return value


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
    # Down/back alerts, from scans and from the live monitor's confirmed
    # transitions. Off by default: phones leaving home would be noise. The
    # transitions are always recorded in the device timeline and uptime.
    alert_on_device_down: bool = False
    alert_on_port_change: bool = True  # a known device opened/closed a probed port
    # Speed / quality metrics
    use_speedtest: bool = True  # latency stats + TCP handshake per device
    speedtest_pings: int = 5  # ICMP echoes per device for jitter/loss
    use_throughput: bool = False  # HTTP download throughput estimate (heavier)
    # Live monitor — continuous background ping of known devices
    live_enabled: bool = True
    live_interval_s: float = 5.0
    live_buffer: int = 180  # samples kept in memory for the live latency chart
    live_max_devices: int = 120  # cap devices probed per tick
    live_down_after: int = 3  # consecutive failed ticks before a device is declared down
    # Internet reference targets pinged every tick (WAN latency/loss). [] = off.
    live_wan_targets: list[str] = Field(default_factory=lambda: ["1.1.1.1", "8.8.8.8"])


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
    pihole: list[PiholeInstance] = Field(default_factory=list)

    # Apprise notification URLs (ntfy://, tgram://, discord://, ...)
    notify_urls: list[str] = Field(default_factory=list)

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'netscan.db'}"


def is_loopback_host(host: str) -> bool:
    """True for localhost / 127.0.0.0/8 / ::1 (names or literal IPs)."""
    host = host.strip().strip("[]").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def require_token_for_bind(host: str, token: str) -> None:
    """Refuse to listen beyond localhost without an API token.

    Without a token every endpoint (scans, integrations and their stored
    credentials) is open to anyone who can reach the port.
    """
    if not token and not is_loopback_host(host):
        raise SystemExit(
            f"Refusing to listen on {host} without an API token: anyone on the network "
            "could use the API. Set NETSCAN_API_TOKEN, or listen on 127.0.0.1."
        )


def load_settings(config_path: str | os.PathLike[str] | None = None) -> Settings:
    """Load settings from YAML file + environment."""
    path = Path(config_path or os.environ.get("NETSCAN_CONFIG", "netscan.yaml"))
    file_data: dict[str, Any] = {}
    if path.is_file():
        with open(path, encoding="utf-8") as fh:
            file_data = yaml.safe_load(fh) or {}
    # An empty key (e.g. ``notify_urls:`` with every entry commented out, as
    # in netscan.example.yaml) loads as None; drop it so the field keeps its
    # default instead of failing validation and stopping the server.
    file_data = {key: value for key, value in file_data.items() if value is not None}
    return Settings(**file_data)
