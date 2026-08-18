"""Integration clients tested against mocked HTTP APIs (respx).

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

import httpx
import pytest
import respx

from netscan.config import AdGuardInstance, ProxmoxInstance, TrueNASInstance
from netscan.integrations import adguard, proxmox, truenas


@respx.mock
def test_proxmox_summary():
    respx.get("https://pve.local:8006/api2/json/version").mock(
        return_value=httpx.Response(200, json={"data": {"version": "8.2.4"}})
    )
    respx.get("https://pve.local:8006/api2/json/cluster/resources").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"type": "node", "node": "pve", "status": "online"},
                    {"type": "qemu", "vmid": 100, "name": "vm1", "status": "running"},
                    {"type": "lxc", "vmid": 101, "name": "ct1", "status": "stopped"},
                ]
            },
        )
    )
    cfg = ProxmoxInstance(name="pve", host="pve.local", token_id="root@pam!t", token_secret="x")
    out = proxmox.collect_all([cfg])
    assert len(out) == 1
    summary = out[0]
    assert summary["version"] == "8.2.4"
    assert summary["guests_total"] == 2
    assert summary["guests_running"] == 1


@respx.mock
def test_proxmox_failure_reported_not_raised():
    respx.get("https://pve.local:8006/api2/json/cluster/resources").mock(
        side_effect=httpx.ConnectError("no route")
    )
    cfg = ProxmoxInstance(name="pve", host="pve.local")
    out = proxmox.collect_all([cfg])
    assert len(out) == 1
    assert "error" in out[0]
    assert out[0]["name"] == "pve"


@respx.mock
def test_truenas_summary():
    respx.get("https://nas.local:443/api/v2.0/system/info").mock(
        return_value=httpx.Response(
            200,
            json={"version": "TrueNAS-SCALE-24.10", "hostname": "nas", "uptime_seconds": 3600, "cores": 8},
        )
    )
    respx.get("https://nas.local:443/api/v2.0/pool").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "tank", "status": "ONLINE"},
                {"name": "backup", "status": "DEGRADED"},
            ],
        )
    )
    respx.get("https://nas.local:443/api/v2.0/disk").mock(return_value=httpx.Response(200, json=[]))
    respx.get("https://nas.local:443/api/v2.0/alert/list").mock(return_value=httpx.Response(200, json=[]))
    cfg = TrueNASInstance(name="nas", host="nas.local", api_key="k")
    out = truenas.collect_all([cfg])
    assert len(out) == 1
    summary = out[0]
    assert summary["version"] == "TrueNAS-SCALE-24.10"
    assert summary["pools_total"] == 2
    assert summary["pools_healthy"] == 1


@respx.mock
def test_adguard_summary():
    respx.get("http://adg.local:80/control/status").mock(
        return_value=httpx.Response(200, json={"version": "v0.107.52"})
    )
    respx.get("http://adg.local:80/control/stats").mock(
        return_value=httpx.Response(
            200,
            json={
                "num_dns_queries": 12345,
                "num_blocked_filtering": 321,
                "avg_processing_time": 0.42,
                "top_queried_domains": [],
                "top_blocked_domains": [],
            },
        )
    )
    respx.get("http://adg.local:80/control/clients").mock(
        return_value=httpx.Response(200, json={"clients": [{"name": "laptop"}]})
    )
    cfg = AdGuardInstance(name="adg", host="adg.local", username="u", password="p")
    out = adguard.collect_all([cfg])
    assert len(out) == 1
    summary = out[0]
    assert summary["version"] == "v0.107.52"
    assert summary["num_dns_queries"] == 12345
    assert len(summary["clients"]) == 1


def test_disabled_instances_skipped():
    cfgs = [
        ProxmoxInstance(name="pve", host="pve.local", enabled=False),
        TrueNASInstance(name="nas", host="nas.local", enabled=False),
        AdGuardInstance(name="adg", host="adg.local", enabled=False),
    ]
    assert proxmox.collect_all([cfgs[0]]) == []
    assert truenas.collect_all([cfgs[1]]) == []
    assert adguard.collect_all([cfgs[2]]) == []


@respx.mock
def test_adguard_unreachable_reports_error():
    # Mocked ConnectError keeps the suite offline and deterministic.
    respx.get("http://adg-down.local:80/control/stats").mock(side_effect=httpx.ConnectError("no route"))
    cfg = AdGuardInstance(name="adg", host="adg-down.local")
    out = adguard.collect_all([cfg])
    assert len(out) == 1
    assert "error" in out[0]


@pytest.mark.parametrize("mod", [proxmox, truenas, adguard])
def test_collect_all_empty(mod):
    assert mod.collect_all([]) == []
