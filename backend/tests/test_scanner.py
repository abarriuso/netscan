"""Scanner unit tests (no network access required).

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from netscan.models import PortInfo
from netscan.scanner import tools
from netscan.scanner.enrich import COMMON_PORTS, EXTENDED_PORTS, detect_os_from_ports


def test_os_detection_windows():
    ports = [PortInfo(port=445, service="SMB"), PortInfo(port=135, service="RPC")]
    assert detect_os_from_ports(ports) == "Windows"


def test_os_detection_linux():
    ports = [PortInfo(port=22, service="SSH"), PortInfo(port=80, service="HTTP")]
    assert detect_os_from_ports(ports) == "Linux/Unix"


def test_os_detection_empty():
    assert detect_os_from_ports([]) == ""


def test_capabilities_detect_returns_dict():
    caps = tools.Capabilities.detect()
    data = caps.as_dict()
    assert "nmap" in data
    assert "mdns" in data
    assert all(isinstance(v, bool) for v in data.values())


def test_tool_specs_have_licenses():
    for spec in tools.TOOLS.values():
        assert spec.license
        assert spec.purpose


def test_run_tool_missing_binary():
    assert tools.run_tool("definitely-not-a-real-binary-xyz", ["--help"]) is None


def test_port_tables_no_duplicates():
    assert len(set(COMMON_PORTS) & set(EXTENDED_PORTS)) == 0


def test_nmap_service_scan_without_nmap(monkeypatch):
    monkeypatch.setitem(tools.TOOLS, "nmap", tools.ToolSpec("nmap", "no-such-bin", "NPSL", "x"))
    assert tools.nmap_service_scan("127.0.0.1", [22]) == {}
