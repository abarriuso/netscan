"""Scan engine orchestration tests (all network access is mocked).

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from netscan.config import ScanDefaults
from netscan.models import HttpInfo
from netscan.scanner import engine


def _caps(tools_available: dict[str, bool] | None = None) -> engine.tools.Capabilities:
    return engine.tools.Capabilities(tools=tools_available or {}, mdns=False)


def _patch_common(monkeypatch, tools_available: dict[str, bool] | None = None) -> None:
    monkeypatch.setattr(
        engine.discovery,
        "arp_scan",
        lambda *a, **k: [
            {"ip": "192.168.1.11", "mac": "aa:bb:cc:dd:ee:02"},
            {"ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:01"},
        ],
    )
    monkeypatch.setattr(
        engine.tools.Capabilities,
        "detect",
        classmethod(lambda cls: _caps(tools_available)),
    )
    monkeypatch.setattr(engine.enrich, "resolve_vendors", lambda macs: {})
    monkeypatch.setattr(engine.enrich, "resolve_hostname", lambda ip: f"host-{ip.rsplit('.', 1)[1]}")
    monkeypatch.setattr(engine.enrich, "ping_host", lambda ip, timeout=1.0: 1.5)
    monkeypatch.setattr(engine.enrich, "scan_ports", lambda ip, ports, workers, timeout: [])


def _cfg(**overrides) -> ScanDefaults:
    base = {
        "use_mdns": False,
        "use_fingerprint": False,
        "use_nmap": False,
        "use_nmap_os": False,
        "use_rustscan": False,
        "use_nuclei": False,
    }
    base.update(overrides)
    return ScanDefaults(**base)


def test_run_scan_aggregates_devices_sorted(monkeypatch):
    _patch_common(monkeypatch)
    result = engine.run_scan(cfg=_cfg(), network="192.168.1.0/24")
    assert result.network == "192.168.1.0/24"
    assert result.total_devices == 2
    assert [d.ip for d in result.devices] == ["192.168.1.10", "192.168.1.11"]
    assert result.devices[0].hostname == "host-10"
    assert result.devices[0].latency_ms == 1.5
    assert result.duration_s >= 0


def test_one_failing_host_does_not_abort_scan(monkeypatch):
    _patch_common(monkeypatch)

    def flaky_ping(ip: str, timeout: float = 1.0):
        if ip.endswith(".11"):
            raise OSError("boom")
        return 1.0

    monkeypatch.setattr(engine.enrich, "ping_host", flaky_ping)
    result = engine.run_scan(cfg=_cfg(), network="192.168.1.0/24")
    assert result.total_devices == 1
    assert result.devices[0].ip == "192.168.1.10"


def test_nuclei_target_cap(monkeypatch):
    _patch_common(monkeypatch, tools_available={"nuclei": True})
    from netscan.models import PortInfo

    monkeypatch.setattr(
        engine.enrich,
        "scan_ports",
        lambda ip, ports, workers, timeout: [PortInfo(port=80, service="HTTP")],
    )
    monkeypatch.setattr(
        engine,
        "fingerprint_http",
        lambda ip, ports: [HttpInfo(url=f"http://{ip}/")],
    )
    captured: list[list[str]] = []
    monkeypatch.setattr(engine.tools, "nuclei_scan", lambda urls: captured.append(urls) or [])

    result = engine.run_scan(
        cfg=_cfg(use_nuclei=True, use_fingerprint=True, nuclei_max_targets=1), network="192.168.1.0/24"
    )
    assert len(captured) == 1
    assert len(captured[0]) == 1  # 2 web UIs discovered, capped to 1
    assert result.vulnerabilities == []


def test_invalid_network_raises(monkeypatch):
    _patch_common(monkeypatch)
    import pytest

    with pytest.raises(ValueError):
        engine.run_scan(cfg=_cfg(), network="not-a-cidr")
