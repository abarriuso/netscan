"""Config loading tests.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from pathlib import Path

from netscan.config import Settings, load_settings


def test_defaults():
    settings = Settings()
    assert settings.scan.workers == 16
    assert settings.api_port == 8600
    assert settings.api_host == "127.0.0.1"
    assert settings.api_token == ""
    assert settings.proxmox == []
    assert settings.truenas == []


def test_yaml_loading(tmp_path: Path):
    cfg = tmp_path / "netscan.yaml"
    cfg.write_text(
        "api_port: 9999\n"
        "scan:\n  network: 10.0.0.0/24\n  full: true\n"
        "proxmox:\n  - name: pve1\n    host: 10.0.0.11\n"
        "    token_id: root@pam!netscan\n"
        "    token_secret: secret\n"
        "truenas:\n  - name: nas\n    host: 10.0.0.12\n    api_key: key\n",
        encoding="utf-8",
    )
    settings = load_settings(cfg)
    assert settings.api_port == 9999
    assert settings.scan.network == "10.0.0.0/24"
    assert settings.scan.full is True
    assert settings.proxmox[0].name == "pve1"
    assert settings.proxmox[0].port == 8006
    assert settings.truenas[0].api_key == "key"


def test_missing_yaml_uses_defaults(tmp_path: Path):
    settings = load_settings(tmp_path / "nope.yaml")
    assert settings.api_port == 8600


def test_db_url_default(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    assert settings.db_url.startswith("sqlite:///")
    assert str(tmp_path) in settings.db_url
