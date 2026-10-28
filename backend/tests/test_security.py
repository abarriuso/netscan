"""Regression tests for the security review fixes.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from netscan.api import deps
from netscan.api.app import create_app
from netscan.config import PiholeInstance, ProxmoxInstance, Settings, require_token_for_bind
from netscan.db.store import InventoryStore
from netscan.integrations import pihole
from netscan.models import Device, ScanResult

TOKEN = "test-token"
AUTH = {"X-API-Key": TOKEN}
LOCAL = "http://127.0.0.1"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _client(tmp_path, token: str = TOKEN, base_url: str = LOCAL) -> TestClient:
    deps.init_state(Settings(data_dir=tmp_path, api_token=token))
    return TestClient(create_app(), base_url=base_url)


def _custom_integration(client: TestClient) -> int:
    resp = client.post(
        "/api/settings/integrations",
        headers=AUTH,
        json={"kind": "custom", "name": "portainer", "config": {"url": "http://portainer.lan"}},
    )
    assert resp.status_code == 201
    return int(resp.json()["id"])


def _proxmox_integration(client: TestClient) -> int:
    resp = client.post(
        "/api/settings/integrations",
        headers=AUTH,
        json={
            "kind": "proxmox",
            "name": "pve",
            "config": {"host": "pve.lan", "token_id": "root@pam!netscan", "token_secret": "PVE-SECRET"},
        },
    )
    assert resp.status_code == 201
    return int(resp.json()["id"])


# --- Logo upload ------------------------------------------------------------ #


def test_logo_upload_requires_token(tmp_path):
    client = _client(tmp_path)
    iid = _custom_integration(client)
    files = {"file": ("x.svg", SVG, "image/svg+xml")}
    assert client.post(f"/api/settings/integrations/{iid}/logo", files=files).status_code == 401
    resp = client.post(f"/api/settings/integrations/{iid}/logo", files=files, headers=AUTH)
    assert resp.status_code == 200


def test_logo_is_public_but_sandboxed(tmp_path):
    client = _client(tmp_path)
    iid = _custom_integration(client)
    files = {"file": ("x.svg", SVG, "image/svg+xml")}
    client.post(f"/api/settings/integrations/{iid}/logo", files=files, headers=AUTH)
    resp = client.get(f"/api/settings/integrations/{iid}/logo")  # no token: <img src>
    assert resp.status_code == 200
    assert "sandbox" in resp.headers["content-security-policy"]
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_other_paths_ending_in_logo_still_need_token(tmp_path):
    client = _client(tmp_path)
    assert client.get("/api/devices/logo").status_code == 401


def test_logo_too_large(tmp_path):
    client = _client(tmp_path)
    iid = _custom_integration(client)
    files = {"file": ("x.png", b"\0" * (2 * 1024 * 1024 + 1), "image/png")}
    resp = client.post(f"/api/settings/integrations/{iid}/logo", files=files, headers=AUTH)
    assert resp.status_code == 413


# --- Integration credentials ----------------------------------------------- #


def test_moving_integration_requires_secret_again(tmp_path):
    client = _client(tmp_path)
    iid = _proxmox_integration(client)
    url = f"/api/settings/integrations/{iid}"
    resp = client.patch(url, headers=AUTH, json={"config": {"host": "other.lan"}})
    assert resp.status_code == 422
    resp = client.patch(url, headers=AUTH, json={"config": {"host": "other.lan", "token_secret": "NEW"}})
    assert resp.status_code == 200


def test_update_without_moving_keeps_secret(tmp_path):
    client = _client(tmp_path)
    iid = _proxmox_integration(client)
    resp = client.patch(
        f"/api/settings/integrations/{iid}",
        headers=AUTH,
        json={"config": {"host": "pve.lan", "port": "8006", "token_secret": "••••••••", "verify_ssl": True}},
    )
    assert resp.status_code == 200
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(url__regex=r"https://pve\.lan:8006/.*").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        client.get("/api/integrations/proxmox", headers=AUTH)
    assert "PVE-SECRET" in route.calls[0].request.headers["authorization"]


@pytest.mark.parametrize(
    "host", ["evil.example/x?", "user@evil.example", "https://pve.lan", "pve.lan:8006", ""]
)
def test_integration_host_must_be_bare(host):
    with pytest.raises(ValueError):
        ProxmoxInstance(name="pve", host=host)


@pytest.mark.parametrize("host", ["pve.lan", "pve", "192.168.1.5", "[::1]"])
def test_integration_host_accepts_names_and_ips(host):
    assert ProxmoxInstance(name="pve", host=host).host == host


def test_custom_url_must_be_http(tmp_path):
    client = _client(tmp_path)
    resp = client.post(
        "/api/settings/integrations",
        headers=AUTH,
        json={"kind": "custom", "name": "x", "config": {"url": "javascript:alert(1)"}},
    )
    assert resp.status_code == 422


# --- Without a token: DNS rebinding and CSRF -------------------------------- #


def test_no_token_rejects_foreign_host(tmp_path):
    client = _client(tmp_path, token="", base_url="http://rebind.attacker.example")
    assert client.get("/api/settings/integrations").status_code == 403


@pytest.mark.parametrize("host", ["127.0.0.1:8600", "localhost:8600", "[::1]:8600"])
def test_no_token_accepts_loopback(tmp_path, host):
    # Host header instead of base_url: Starlette's TestClient can't parse an
    # IPv6 base_url such as http://[::1]:8600.
    client = _client(tmp_path, token="")
    assert client.get("/api/health", headers={"Host": host}).status_code == 200


def test_token_allows_lan_host(tmp_path):
    client = _client(tmp_path, base_url="http://192.168.1.10:8600")
    assert client.get("/api/health", headers=AUTH).status_code == 200


def test_cross_origin_write_refused(tmp_path):
    client = _client(tmp_path, token="")
    resp = client.post("/api/alerts/1/ack", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403


def test_same_origin_write_allowed(tmp_path):
    client = _client(tmp_path, token="", base_url="http://127.0.0.1:8600")
    resp = client.post("/api/alerts/1/ack", headers={"Origin": "http://127.0.0.1:8600"})
    assert resp.status_code == 404  # reached the endpoint: no such alert


# TestClient.websocket_connect ignores base_url (always ws://testserver), so
# the WebSocket tests set Host themselves.
WS_PATHS = ["/ws/progress", "/ws/events"]


@pytest.mark.parametrize("path", WS_PATHS)
def test_websocket_same_origin_allowed(tmp_path, path):
    client = _client(tmp_path, token="")
    headers = {"Host": "127.0.0.1:8600", "Origin": "http://127.0.0.1:8600"}
    with client.websocket_connect(path, headers=headers) as ws:
        assert ws.receive_json()


@pytest.mark.parametrize("path", WS_PATHS)
def test_websocket_cross_origin_refused(tmp_path, path):
    client = _client(tmp_path, token="")
    headers = {"Host": "127.0.0.1:8600", "Origin": "https://evil.example"}
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(path, headers=headers) as ws:
        ws.receive_text()


@pytest.mark.parametrize("path", WS_PATHS)
def test_websocket_foreign_host_refused_without_token(tmp_path, path):
    client = _client(tmp_path, token="")
    headers = {"Host": "rebind.attacker.example:8600"}
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(path, headers=headers) as ws:
        ws.receive_text()


def test_refuses_public_bind_without_token():
    with pytest.raises(SystemExit):
        require_token_for_bind("0.0.0.0", "")
    require_token_for_bind("0.0.0.0", TOKEN)
    require_token_for_bind("127.0.0.1", "")
    require_token_for_bind("localhost", "")


# --- Scan size ------------------------------------------------------------- #


def test_scan_network_too_large(tmp_path):
    client = _client(tmp_path)
    assert client.post("/api/scans", headers=AUTH, json={"network": "10.0.0.0/8"}).status_code == 400


# --- Online state ---------------------------------------------------------- #


def _scan(network: str, devices: list[Device]) -> ScanResult:
    return ScanResult(network=network, total_devices=len(devices), devices=devices)


def test_missing_device_goes_offline_without_alerts():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_scan("192.168.1.0/24", [Device(ip="192.168.1.50", mac="aa:bb:cc:dd:ee:ff")]))
    alerts = store.record_scan(_scan("192.168.1.0/24", []), alert_on_down=False)
    assert alerts == []
    assert store.list_devices()[0].online is False


def test_scan_of_other_network_keeps_state():
    store = InventoryStore("sqlite:///:memory:")
    store.record_scan(_scan("192.168.1.0/24", [Device(ip="192.168.1.50", mac="aa:bb:cc:dd:ee:ff")]))
    store.record_scan(_scan("10.0.0.0/24", []))
    assert store.list_devices()[0].online is True


# --- Pi-hole sessions ------------------------------------------------------ #


def test_pihole_reuses_its_session_across_polls():
    # Pi-hole v6 caps concurrent API sessions: logging in on every poll used
    # them all up and locked out its web UI too.
    pihole._SESSIONS.clear()
    cfg = PiholeInstance(name="ph", host="ph.lan", password="p")
    with respx.mock() as mock:
        login = mock.post("http://ph.lan:80/api/auth").mock(
            return_value=httpx.Response(200, json={"session": {"valid": True, "sid": "abc"}})
        )
        stats = mock.get("http://ph.lan:80/api/stats/summary").mock(return_value=httpx.Response(200, json={}))
        for _ in range(3):
            assert "error" not in pihole.collect_all([cfg])[0]
    assert login.call_count == 1
    assert [call.request.headers["sid"] for call in stats.calls] == ["abc"] * 3


def test_reverse_proxy_origin_allowed(tmp_path):
    client = _client(tmp_path, base_url="http://127.0.0.1:8600")
    headers = {**AUTH, "Origin": "https://netscan.example", "X-Forwarded-Host": "netscan.example"}
    assert client.post("/api/alerts/1/ack", headers=headers).status_code == 404
