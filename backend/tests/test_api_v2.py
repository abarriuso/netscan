"""API tests for the observability / insights / toolbox endpoints and the
security fixes.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from fastapi.testclient import TestClient

from netscan.api import deps
from netscan.api.app import _tail, create_app
from netscan.config import Settings
from netscan.events import emit
from netscan.models import Device, PortInfo, ScanResult


def _client(tmp_path, **settings) -> TestClient:
    deps.init_state(Settings(data_dir=tmp_path, **settings))
    return TestClient(create_app(), base_url="http://127.0.0.1")


def _seed(state):
    state.store.record_scan(
        ScanResult(
            network="192.168.1.0/24",
            devices=[
                Device(
                    ip="192.168.1.10", mac="aa:bb:cc:dd:ee:01", latency_ms=1.0, open_ports=[PortInfo(port=23)]
                )
            ],
            ports_scanned=[22, 23, 80],
        )
    )


def test_logo_upload_requires_the_token(tmp_path):
    client = _client(tmp_path, api_token="s3cret")
    resp = client.post(
        "/api/settings/integrations/1/logo", files={"file": ("x.png", b"\x89PNG", "image/png")}
    )
    assert resp.status_code == 401
    # Reading a logo stays public (it is used in <img src>); 404 because none exists.
    assert client.get("/api/settings/integrations/1/logo").status_code == 404


def test_metrics_endpoint_requires_token_and_serves_text(tmp_path):
    client = _client(tmp_path, api_token="s3cret")
    assert client.get("/metrics").status_code == 401
    resp = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "netscan_devices" in resp.text


def test_events_endpoint_returns_new_events(tmp_path):
    client = _client(tmp_path)
    last = client.get("/api/events?since=0&limit=1").json()["last_seq"]
    emit("scan", "hello from the test")
    out = client.get(f"/api/events?since={last}").json()
    assert any(e["msg"] == "hello from the test" for e in out["events"])
    assert client.get("/api/events/stats").json()["last_seq"] >= last + 1


def test_api_calls_are_echoed_to_the_feed(tmp_path):
    client = _client(tmp_path)
    last = client.get("/api/events?since=0&limit=1").json()["last_seq"]
    client.get("/api/devices")
    events = client.get(f"/api/events?since={last}&sources=api").json()["events"]
    assert any("GET /api/devices → 200" in e["msg"] for e in events)


def test_insight_endpoints_with_seeded_inventory(tmp_path):
    client = _client(tmp_path)
    _seed(deps.get_state())
    up = client.get("/api/uptime?hours=24&slots=12").json()
    assert up["devices"][0]["mac"] == "aa:bb:cc:dd:ee:01"
    assert len(up["devices"][0]["timeline"]) == 12
    sec = client.get("/api/security").json()
    assert sec["devices"][0]["score"] > 0
    assert sec["exposure"][0]["port"] == 23
    m = client.get("/api/map").json()
    assert any(n["ip"] == "192.168.1.10" for n in m["nodes"])
    ipmap = client.get("/api/ipmap?network=192.168.1.0/28").json()
    assert ipmap["size"] == 16
    prof = client.get("/api/devices/aa:bb:cc:dd:ee:01/profile").json()
    assert prof["risk"]["level"] in {"medium", "high", "critical"}
    assert prof["classification"]["role"]
    tl = client.get("/api/devices/aa:bb:cc:dd:ee:01/timeline").json()
    assert tl["events"][0]["kind"] == "new"
    csv_resp = client.get("/api/export/devices?format=csv")
    assert csv_resp.status_code == 200
    assert csv_resp.text.splitlines()[0].startswith("ip,mac,hostname")
    assert "risk_score_0_100" in csv_resp.text
    assert client.get("/api/export/devices?format=json").json()[0]["ip"] == "192.168.1.10"


def test_ipmap_rejects_large_networks(tmp_path):
    client = _client(tmp_path)
    assert client.get("/api/ipmap?network=10.0.0.0/16").status_code == 400


def test_patch_notes_only(tmp_path):
    client = _client(tmp_path)
    _seed(deps.get_state())
    assert client.patch("/api/devices/aa:bb:cc:dd:ee:01", json={"notes": "printer room"}).status_code == 200
    assert client.get("/api/devices").json()[0]["notes"] == "printer room"
    assert client.patch("/api/devices/aa:bb:cc:dd:ee:01", json={}).status_code == 422


def test_toolbox_validation(tmp_path):
    client = _client(tmp_path)
    assert client.post("/api/tools/subnet", json={"cidr": "10.1.2.3/30"}).json()["usable_hosts"] == 2
    assert client.post("/api/tools/subnet", json={"cidr": "bad"}).status_code == 400
    assert client.post("/api/tools/portscan", json={"target": "8.8.8.8"}).status_code == 400
    assert (
        client.post("/api/tools/portscan", json={"target": "192.168.1.1", "ports": "1-99999"}).status_code
        == 400
    )
    assert client.post("/api/tools/ping", json={"target": "-nope"}).status_code == 400
    assert client.post("/api/tools/mac", json={"mac": "zz"}).status_code == 400


def test_scan_conflict_is_reported_synchronously(tmp_path):
    client = _client(tmp_path)
    state = deps.get_state()
    state.scan_lock.acquire()
    try:
        assert client.post("/api/scans", json={}).status_code == 409
    finally:
        state.scan_lock.release()


def test_ack_all_alerts(tmp_path):
    client = _client(tmp_path)
    _seed(deps.get_state())
    assert client.post("/api/alerts/ack-all").json()["acknowledged"] == 1


def test_tail_reads_only_the_end(tmp_path):
    log = tmp_path / "big.log"
    log.write_text("".join(f"line {i}\n" for i in range(50000)), encoding="utf-8")
    assert _tail(log, 3) == ["line 49997", "line 49998", "line 49999"]
