"""Diagnostics toolbox tests (pure parts + a fake DNS server).

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

import socket
import struct
import threading

import pytest

from netscan import diag


def test_validate_target():
    assert diag.validate_target("192.168.1.1") == "192.168.1.1"
    assert diag.validate_target("nas.lan") == "nas.lan"
    for bad in ("", "-bad.example", "a b", "x" * 300, "http://x"):
        with pytest.raises(diag.DiagError):
            diag.validate_target(bad)


def test_subnet_calculator():
    s = diag.subnet("192.168.1.77/26")
    assert s["network"] == "192.168.1.64"
    assert s["broadcast"] == "192.168.1.127"
    assert s["netmask"] == "255.255.255.192"
    assert s["wildcard"] == "0.0.0.63"
    assert s["usable_hosts"] == 62
    assert s["first_host"] == "192.168.1.65"
    assert s["last_host"] == "192.168.1.126"
    assert s["private"] is True
    assert diag.subnet("10.0.0.1/32")["usable_hosts"] == 1
    with pytest.raises(diag.DiagError):
        diag.subnet("nope")


def test_ping_aggregates(monkeypatch):
    seq = iter([1.0, None, 3.0])
    monkeypatch.setattr(diag.icmp, "echo", lambda ip, timeout: next(seq))
    monkeypatch.setattr(diag.time, "sleep", lambda _s: None)
    r = diag.ping("10.0.0.1", count=3)
    assert r["loss_pct"] == pytest.approx(33.3)
    assert r["min_ms"] == 1.0 and r["max_ms"] == 3.0 and r["avg_ms"] == 2.0
    assert r["jitter_ms"] == 2.0


def _dns_response(query: bytes) -> bytes:
    qid = query[:2]
    question = query[12:]
    header = qid + struct.pack("!HHHHH", 0x8180, 1, 2, 0, 0)
    # answer 1: A 93.184.216.34 (name via compression pointer to offset 12)
    a = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 300, 4) + socket.inet_aton("93.184.216.34")
    # answer 2: MX-like TXT record to exercise the TXT parser
    txt = b"\x05hello\x05world"
    t = b"\xc0\x0c" + struct.pack("!HHIH", 16, 1, 60, len(txt)) + txt
    return header + question + a + t


def test_dns_query_against_fake_server(monkeypatch):
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]

    def serve():
        data, addr = srv.recvfrom(512)
        srv.sendto(_dns_response(data), addr)

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    real_sendto = socket.socket.sendto

    class PortRedirect(socket.socket):
        def sendto(self, data, address):  # type: ignore[override]
            return real_sendto(self, data, (address[0], port))

    monkeypatch.setattr(diag.socket, "socket", PortRedirect)
    r = diag.dns_query("example.com", "A", "127.0.0.1")
    srv.close()
    assert r["rcode"] == "NOERROR"
    assert r["answers"][0] == {"name": "example.com.", "type": "A", "ttl_s": 300, "data": "93.184.216.34"}
    assert r["answers"][1]["data"] == '"hello" "world"'
    assert r["ms"] is not None and r["ms"] >= 0


def test_dns_query_validates_inputs():
    with pytest.raises(diag.DiagError):
        diag.dns_query("example.com", "BOGUS")
    with pytest.raises(diag.DiagError):
        diag.dns_query("example.com", "A", "not-an-ip")


def test_read_name_survives_pointer_loops():
    data = b"\x00" * 12 + b"\xc0\x0c"  # pointer to itself
    name, _ = diag._read_name(data, 12)
    assert name == "."


def test_http_check_rejects_bad_scheme():
    with pytest.raises(diag.DiagError):
        diag.http_check("ftp://example.com/")


def test_tcp_check_against_local_listener():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    port = srv.getsockname()[1]
    r = diag.tcp_check("127.0.0.1", port, count=2)
    srv.close()
    assert r["open"] is True
    assert len(r["connect_ms"]) == 2
