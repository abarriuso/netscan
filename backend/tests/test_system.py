"""Tests for the system/host status module.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

from netscan import system


def test_collect_has_all_sections():
    snap = system.collect()
    for key in ("timestamp", "host", "cpu", "memory", "disks", "network", "process", "frontend"):
        assert key in snap


def test_host_info_basic():
    host = system.host_info()
    assert host["hostname"]
    assert host["os"]
    assert "arch" in host


def test_process_info_reports_pid():
    proc = system.process_info()
    assert proc["pid"] > 0
    assert proc["uptime_seconds"] >= 0
    assert proc["python"]


def test_frontend_status_shape(tmp_path):
    # No dist dir provided and none adjacent in a tmp cwd -> not built.
    status = system.frontend_status(tmp_path / "does-not-exist")
    assert status["built"] is False


def test_frontend_status_detects_built(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "app.js").write_text("console.log(1)", encoding="utf-8")
    status = system.frontend_status(dist)
    assert status["built"] is True
    assert status["files"] == 2
    assert status["size_bytes"] > 0


def test_network_info_returns_interfaces():
    net = system.network_info()
    assert "interfaces" in net
    assert isinstance(net["interfaces"], list)


def test_cpu_and_memory_available_when_psutil_present():
    # In CI psutil is a hard dependency, so these should be populated.
    if system.psutil is None:
        return
    assert system.cpu_info()["available"] is True
    assert system.memory_info()["available"] is True
