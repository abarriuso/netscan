"""Role inference, MAC analysis and risk scoring tests.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from datetime import datetime, timedelta

from netscan.classify import classify, mac_info
from netscan.security import assess, level_for


def test_mac_info_flags_randomized_and_virtual():
    phone = mac_info("da:a1:19:00:00:01")  # 0xda has the locally-administered bit
    assert phone.locally_administered and phone.as_dict()["randomized"]
    vm = mac_info("bc:24:11:aa:bb:cc")
    assert vm.virtual_platform == "Proxmox VE"
    assert not vm.as_dict()["randomized"]
    docker = mac_info("02:42:ac:11:00:02")
    assert docker.virtual_platform == "Docker"
    assert not mac_info("d4:86:60:f9:46:5e").locally_administered


def test_gateway_and_self_win_outright():
    assert classify(ip="192.168.1.1", gateway_ip="192.168.1.1").role == "gateway"
    assert classify(ip="192.168.1.5", local_ip="192.168.1.5").role == "netscan"


def test_ports_outrank_vendor_hint():
    c = classify(ip="10.0.0.2", vendor="Raspberry Pi Trading", ports={22, 8006})
    assert c.role == "hypervisor"
    assert any("8006" in r for r in c.reasons)


def test_mdns_and_vendor_signals():
    assert classify(ip="10.0.0.3", mdns_services=["googlecast"]).role == "media"
    assert classify(ip="10.0.0.4", vendor="Espressif Inc.").role == "iot"
    assert classify(ip="10.0.0.5", ports={9100, 80}).role == "printer"
    assert classify(ip="10.0.0.6", ports={3389, 135, 445}).role == "workstation"


def test_isp_router_sharing_smb_is_network_gear_not_a_pc():
    # Orange Livebox: Sagemcom OUI, hostname LIVEBOX, SMB share of a USB disk.
    c = classify(
        ip="192.168.1.2", vendor="Sagemcom Broadband SAS", hostname="LIVEBOX", ports={53, 80, 139, 443, 445}
    )
    assert c.role == "network"


def test_windows_ports_still_win_for_a_pc():
    assert (
        classify(ip="10.0.0.8", vendor="Sagemcom Broadband SAS", ports={135, 139, 445}).role == "workstation"
    )


def test_unknown_when_no_signal():
    c = classify(ip="10.0.0.9", mac="d4:86:60:f9:46:5e")
    assert c.role == "unknown"
    assert c.confidence == 0


def test_random_mac_alone_suggests_mobile():
    assert classify(ip="10.0.0.7", mac="5a:11:22:33:44:55").role == "mobile"


def test_risk_scale_boundaries():
    assert level_for(0) == "low"
    assert level_for(19) == "low"
    assert level_for(20) == "medium"
    assert level_for(45) == "high"
    assert level_for(70) == "critical"


def test_trusted_quiet_device_scores_zero():
    risk = assess(
        {
            "trusted": True,
            "mac": "d4:86:60:f9:46:5e",
            "first_seen": datetime.now() - timedelta(days=90),
            "ports": [{"port": 22}],
        }
    )
    assert risk["score"] == 0
    assert risk["level"] == "low"
    assert risk["factors"] == []


def test_risky_ports_tls_and_findings_add_up_with_evidence():
    device = {
        "trusted": False,
        "mac": "d4:86:60:f9:46:5e",
        "first_seen": datetime.now() - timedelta(days=30),
        "ports": [{"port": 23, "version": "BusyBox telnetd"}, {"port": 443}],
    }
    scan_dev = {
        "http": [
            {
                "url": "https://10.0.0.2:443/",
                "tls": {"days_remaining": -3, "version": "TLSv1.1", "self_signed": True},
            },
        ]
    }
    findings = [
        {
            "tool": "nuclei",
            "template": "cve-x",
            "severity": "high",
            "name": "CVE-X",
            "matched_at": "https://10.0.0.2/",
        }
    ]
    risk = assess(device, scan_dev, findings)
    ids = {f["id"] for f in risk["factors"]}
    assert {"untrusted", "port-23", "finding-nuclei-cve-x"} <= ids
    assert any(i.startswith("cert-expired") for i in ids)
    assert any(i.startswith("weak-tls") for i in ids)
    assert risk["score"] == 100  # capped
    assert risk["level"] == "critical"
    telnet = next(f for f in risk["factors"] if f["id"] == "port-23")
    assert "BusyBox" in telnet["evidence"]
    assert telnet["remediation"]
    # factors are ordered by weight
    points = [f["points"] for f in risk["factors"]]
    assert points == sorted(points, reverse=True)


def test_new_device_and_conflict_factors():
    device = {
        "trusted": True,
        "mac": "d4:86:60:f9:46:5e",
        "first_seen": datetime.now().isoformat(),
        "ports": [],
    }
    risk = assess(device, conflict_macs=["aa:aa:aa:aa:aa:aa"])
    ids = {f["id"] for f in risk["factors"]}
    assert ids == {"new", "ip-conflict"}
    assert risk["score"] == 40
