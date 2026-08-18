"""API smoke tests.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from fastapi.testclient import TestClient

from netscan.api import deps
from netscan.api.app import create_app
from netscan.config import Settings


def _client(tmp_path) -> TestClient:
    deps.init_state(Settings(data_dir=tmp_path))
    app = create_app()
    return TestClient(app)


def test_health(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_capabilities(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    assert "capabilities" in resp.json()


def test_overview_empty(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/overview")
    assert resp.status_code == 200
    assert resp.json()["devices_total"] == 0


def test_latest_scan_404_when_empty(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/api/scans/latest")
    assert resp.status_code == 404


def test_integrations_empty(tmp_path):
    client = _client(tmp_path)
    for path in ("/api/integrations/proxmox", "/api/integrations/truenas", "/api/integrations/adguard"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.json() == []
