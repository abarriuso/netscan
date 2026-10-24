"""ICMP backend and unprivileged discovery tests (no real network).

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

import subprocess

from netscan.scanner import discovery, icmp

WIN_ARP = """
Interfaz: 192.168.1.204 --- 0x7
  Dirección de Internet          Dirección física      Tipo
  192.168.1.1           d4-86-60-f9-46-5e     dinámico
  192.168.1.2           cc-00-f1-bd-1c-e0     dinámico
  192.168.1.255         ff-ff-ff-ff-ff-ff     estático
  224.0.0.22            01-00-5e-00-00-16     estático
"""

LINUX_ARP = """IP address       HW type     Flags       HW address            Mask     Device
192.168.1.1      0x1         0x2         d4:86:60:f9:46:5e     *        eth0
192.168.1.77     0x1         0x0         00:00:00:00:00:00     *        eth0
192.168.1.9      0x1         0x2         aa:bb:cc:dd:ee:09     *        eth0
"""

BSD_ARP = """? (192.168.1.1) at d4:86:60:f9:46:5e on en0 ifscope [ethernet]
? (192.168.1.3) at 0:1b:2:3:4:a on en0 ifscope [ethernet]
? (192.168.1.8) at (incomplete) on en0 ifscope [ethernet]
"""


def test_parse_windows_arp_table_skips_broadcast_and_multicast():
    table = discovery.parse_neighbor_output(WIN_ARP, "Windows")
    assert table == {"192.168.1.1": "d4:86:60:f9:46:5e", "192.168.1.2": "cc:00:f1:bd:1c:e0"}


def test_parse_linux_proc_arp_skips_incomplete():
    table = discovery.parse_neighbor_output(LINUX_ARP, "Linux")
    assert table == {"192.168.1.1": "d4:86:60:f9:46:5e", "192.168.1.9": "aa:bb:cc:dd:ee:09"}


def test_parse_bsd_arp_pads_octets():
    table = discovery.parse_neighbor_output(BSD_ARP, "Darwin")
    assert table == {"192.168.1.1": "d4:86:60:f9:46:5e", "192.168.1.3": "00:1b:02:03:04:0a"}


def test_normalize_mac_variants():
    assert discovery.normalize_mac("D4-86-60-F9-46-5E") == "d4:86:60:f9:46:5e"
    assert discovery.normalize_mac("0:1b:2:3:4:a") == "00:1b:02:03:04:0a"
    assert discovery.normalize_mac("d486.60f9.465e") == "d4:86:60:f9:46:5e"


def test_sweep_merges_icmp_answers_with_arp_cache(monkeypatch):
    monkeypatch.setattr(icmp, "echo", lambda ip, timeout=1.0: 0.5 if ip == "192.168.1.1" else None)
    monkeypatch.setattr(
        discovery,
        "neighbor_table",
        lambda: {
            "192.168.1.1": "d4:86:60:f9:46:5e",
            "192.168.1.40": "aa:bb:cc:00:00:40",
            "10.9.9.9": "aa:aa:aa:aa:aa:aa",
        },
    )
    devices = discovery.sweep_scan("192.168.1.0/28")
    # .1 answered ICMP (and is in the cache); .40 is outside the /28 → dropped;
    # 10.9.9.9 is in another network → dropped.
    assert devices == [{"ip": "192.168.1.1", "mac": "d4:86:60:f9:46:5e"}]


def test_sweep_refuses_huge_networks():
    import pytest

    with pytest.raises(discovery.ScanPrereqError, match="too large"):
        discovery.sweep_scan("10.0.0.0/16")


def test_discover_hosts_falls_back_without_privileges(monkeypatch):
    monkeypatch.setattr(discovery, "is_elevated", lambda: False)
    monkeypatch.setattr(
        discovery, "sweep_scan", lambda cidr, progress=None: [{"ip": "192.168.1.5", "mac": ""}]
    )
    devices, method = discovery.discover_hosts("192.168.1.0/24")
    assert method == "sweep"
    assert devices[0]["ip"] == "192.168.1.5"


def test_subprocess_echo_rejects_unreachable_reply(monkeypatch):
    """Windows ping exits 0 for 'Destination host unreachable' — no TTL → not a reply."""
    out = "Respuesta desde 192.168.1.204: Host de destino inaccesible.\n"
    monkeypatch.setattr(
        icmp.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out, stderr="")
    )
    assert icmp._subprocess_echo("192.168.1.99", 1.0) is None


def test_subprocess_echo_parses_time_and_sub_ms_bound(monkeypatch):
    replies = iter(
        [
            "64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=0.412 ms\n",
            "Respuesta desde 10.0.0.1: bytes=32 tiempo<1m TTL=64\n".replace("<1m", "<1ms"),
        ]
    )
    monkeypatch.setattr(
        icmp.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=next(replies), stderr=""),
    )
    assert icmp._subprocess_echo("10.0.0.1", 1.0) == 0.412
    assert icmp._subprocess_echo("10.0.0.1", 1.0) == 0.5  # "<1 ms" → midpoint of [0, 1)


def test_checksum_matches_rfc1071_example():
    # RFC 1071 example words: 0x0001 f203 f4f5 f6f7 → sum 0xddf2, checksum 0x220d
    assert icmp._checksum(bytes.fromhex("0001f203f4f5f6f7")) == 0x220D


def test_backend_name_is_known():
    assert icmp.backend() in {"win-api", "dgram", "raw", "subprocess"}
