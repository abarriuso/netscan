"""Discovery prereq tests.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

import pytest

from netscan.scanner import discovery


def test_arp_scan_requires_elevation(monkeypatch):
    monkeypatch.setattr(discovery, "is_elevated", lambda: False)
    with pytest.raises(discovery.ScanPrereqError, match="administrador"):
        discovery.arp_scan("192.168.1.0/24")


def test_is_elevated_returns_bool():
    assert isinstance(discovery.is_elevated(), bool)


def test_get_local_network_fallback():
    cidr, _ip, iface = discovery.get_local_network()
    assert cidr.endswith("/24") or "/" in cidr
    assert iface
