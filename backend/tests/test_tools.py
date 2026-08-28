"""Tests for external-tool wrappers and Wake-on-LAN.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

import subprocess

import pytest

from netscan import wol
from netscan.scanner import tools


def test_rustscan_parse(monkeypatch):
    monkeypatch.setattr(
        tools,
        "run_tool",
        lambda b, a, timeout=0: "Open 192.168.1.1:22\n192.168.1.1 -> [22,80,443,8006]\n",
    )
    assert tools.rustscan_ports("192.168.1.1") == [22, 80, 443, 8006]


def test_rustscan_no_output(monkeypatch):
    monkeypatch.setattr(tools, "run_tool", lambda b, a, timeout=0: None)
    assert tools.rustscan_ports("192.168.1.1") == []


def test_nuclei_parse_line():
    line = (
        '{"template-id":"proxmox-panel","info":{"severity":"medium","name":"Proxmox Panel"},'
        '"matched-at":"https://192.168.1.11:8006"}'
    )
    parsed = tools.parse_nuclei_line(line)
    assert parsed is not None
    assert parsed["severity"] == "medium"
    assert parsed["template"] == "proxmox-panel"


def test_nuclei_parse_garbage():
    assert tools.parse_nuclei_line("not json at all") is None


def test_nuclei_empty_urls():
    assert tools.nuclei_scan([]) == []


def test_whatweb_scan_parses_technologies(monkeypatch):
    monkeypatch.setattr(
        tools,
        "run_tool",
        lambda b, a, timeout=0: "http://192.168.1.1 [200 OK] Apache[2.4.1], PHP[8.1]\n",
    )
    assert tools.whatweb_scan("http://192.168.1.1") == ["Apache[2.4.1]", "PHP[8.1]"]


def test_whatweb_scan_no_binary(monkeypatch):
    monkeypatch.setattr(tools, "run_tool", lambda b, a, timeout=0: None)
    assert tools.whatweb_scan("http://192.168.1.1") == []


def test_testssl_scan_missing_binary(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda b: None)
    assert tools.testssl_scan("192.168.1.1:443") == []


def test_testssl_scan_parses_and_filters_findings(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda b: "/usr/bin/testssl.sh")

    def fake_run(cmd, **kwargs):
        json_arg = next(a for a in cmd if a.startswith("--jsonfile="))
        out_path = json_arg.split("=", 1)[1]
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(
                '[{"id": "cert_numbers", "severity": "OK", "finding": "1 cert"},'
                '{"id": "TLS1", "severity": "MEDIUM", "finding": "offered"}]'
            )

    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    findings = tools.testssl_scan("192.168.1.1:443")
    assert findings == [
        {
            "tool": "testssl",
            "template": "TLS1",
            "severity": "medium",
            "name": "offered",
            "matched_at": "192.168.1.1:443",
        }
    ]


def test_testssl_scan_timeout_returns_empty(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda b: "/usr/bin/testssl.sh")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    assert tools.testssl_scan("192.168.1.1:443") == []


def test_wol_rejects_bad_mac():
    with pytest.raises(ValueError, match="MAC inválida"):
        wol.wake("not-a-mac")


def test_wol_sends_magic_packet(monkeypatch):
    sent: list[bytes] = []

    class FakeSocket:
        def __init__(self, *a, **kw):
            pass

        def setsockopt(self, *a):
            pass

        def sendto(self, packet, addr):
            sent.append(packet)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    import socket

    monkeypatch.setattr(socket, "socket", FakeSocket)
    monkeypatch.setattr(wol, "_default_broadcast", lambda: "192.168.1.255")
    monkeypatch.setattr(wol.time, "sleep", lambda _: None)
    wol.wake("AA:BB:CC:DD:EE:FF")
    assert len(sent) == 3  # repeated to survive packet loss
    packet = sent[0]
    assert packet[:6] == b"\xff" * 6
    assert packet[6:12] == bytes.fromhex("aabbccddeeff")
    assert len(packet) == 6 + 16 * 6
