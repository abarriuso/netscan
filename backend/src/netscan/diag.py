"""Diagnostics toolbox: ping, traceroute, DNS, TCP, HTTP timing, TLS,
subnet and MAC lookups.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Every tool streams its progress to the event bus (source ``toolbox``) —
the dashboard terminal shows each echo/hop/phase as it happens — and
returns a structured result. Time is always milliseconds (float), sizes
bytes, rates Mbit/s (10^6 bit/s).

No external binaries are needed: ICMP and TTL-limited probes use the same
native backends as the scanner (scanner.icmp); DNS is a minimal RFC 1035
client so any resolver can be queried and timed directly (the OS resolver
API hides which server answered and how long it took).
"""

from __future__ import annotations

import contextlib
import ctypes
import ipaddress
import os
import random
import re
import socket
import ssl
import struct
import subprocess
import time
from itertools import pairwise
from statistics import fmean, pstdev
from typing import Any
from urllib.parse import urlsplit

from netscan.events import emit, fmt_ms
from netscan.scanner import icmp

_HOST_RE = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.?$")


class DiagError(ValueError):
    """Invalid input for a diagnostic tool (→ HTTP 400)."""


def validate_target(target: str) -> str:
    target = (target or "").strip()
    try:
        ipaddress.ip_address(target)
        return target
    except ValueError:
        pass
    if not _HOST_RE.match(target):
        raise DiagError(f"Not an IP address or hostname: {target!r}")
    return target


def resolve(target: str) -> tuple[str, float]:
    """Hostname → first IPv4 + resolution time in ms (0 for literal IPs)."""
    try:
        ipaddress.IPv4Address(target)
        return target, 0.0
    except ValueError:
        pass
    start = time.perf_counter()
    try:
        infos = socket.getaddrinfo(target, None, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise DiagError(f"Cannot resolve {target}: {exc}") from exc
    elapsed = (time.perf_counter() - start) * 1000
    ip = str(infos[0][4][0])
    emit("toolbox", f"resolve {target} → {ip} ({fmt_ms(elapsed)})", target=target, ip=ip)
    return ip, round(elapsed, 3)


# --------------------------------------------------------------------------- #
# ping
# --------------------------------------------------------------------------- #
def ping(target: str, count: int = 5, timeout: float = 1.0, interval: float = 0.2) -> dict[str, Any]:
    target = validate_target(target)
    count = max(1, min(int(count), 50))
    ip, dns_ms = resolve(target)
    emit(
        "toolbox",
        f"PING {target} ({ip}) · {count} echoes · timeout {int(timeout * 1000)} ms · backend {icmp.backend()}",
    )
    rtts: list[float | None] = []
    for seq in range(1, count + 1):
        rtt = icmp.echo(ip, timeout)
        rtts.append(rtt)
        emit(
            "toolbox",
            f"icmp_seq={seq} {ip} " + (f"time={fmt_ms(rtt)}" if rtt is not None else "timeout"),
            "info" if rtt is not None else "warning",
        )
        if seq < count:
            time.sleep(interval)
    ok = [r for r in rtts if r is not None]
    stats = {
        "min_ms": round(min(ok), 3) if ok else None,
        "avg_ms": round(fmean(ok), 3) if ok else None,
        "max_ms": round(max(ok), 3) if ok else None,
        "stddev_ms": round(pstdev(ok), 3) if len(ok) > 1 else (0.0 if ok else None),
        "jitter_ms": round(fmean(abs(b - a) for a, b in pairwise(ok)), 3) if len(ok) > 1 else None,
        "loss_pct": round(100 * (count - len(ok)) / count, 1),
    }
    emit(
        "toolbox",
        f"--- {target} ping statistics: {count} sent, {len(ok)} received, {stats['loss_pct']} % loss · "
        f"rtt min/avg/max/stddev = {fmt_ms(stats['min_ms'])}/{fmt_ms(stats['avg_ms'])}/{fmt_ms(stats['max_ms'])}/"
        f"{fmt_ms(stats['stddev_ms'])}",
    )
    return {"target": target, "ip": ip, "dns_ms": dns_ms, "count": count, "rtts_ms": rtts, **stats}


# --------------------------------------------------------------------------- #
# traceroute
# --------------------------------------------------------------------------- #
def _win_ttl_echo(ip: str, ttl: int, timeout: float) -> tuple[str | None, float | None, int]:
    """One TTL-limited echo through IcmpSendEcho → (responder, rtt ms, status)."""
    lib = icmp._win_lib()
    handle = lib.IcmpCreateFile()
    options = icmp._IpOptionInformation(Ttl=ttl)
    payload = b"netscan-trace"
    size = ctypes.sizeof(icmp._IcmpEchoReply) + len(payload) + 8
    buf = ctypes.create_string_buffer(size)
    try:
        start = time.perf_counter()
        n = lib.IcmpSendEcho(
            handle,
            icmp._in_addr(ip),
            payload,
            len(payload),
            ctypes.byref(options),
            buf,
            size,
            int(timeout * 1000),
        )
        elapsed = (time.perf_counter() - start) * 1000
    finally:
        lib.IcmpCloseHandle(handle)
    reply = icmp._IcmpEchoReply.from_buffer(buf)
    if not n and reply.Status == 0:
        return None, None, 11010
    responder = socket.inet_ntoa(struct.pack("<L", reply.Address)) if reply.Address else None
    # 0 = reached the target, 11013 = TTL expired in transit (a router hop)
    if reply.Status in (0, 11013):
        return responder, round(elapsed, 3), reply.Status
    return responder, None, reply.Status


def traceroute(target: str, max_hops: int = 20, timeout: float = 1.0) -> dict[str, Any]:
    target = validate_target(target)
    max_hops = max(1, min(int(max_hops), 30))
    ip, _ = resolve(target)
    emit("toolbox", f"traceroute to {target} ({ip}), {max_hops} hops max, {int(timeout * 1000)} ms per probe")
    hops: list[dict[str, Any]] = []
    if icmp.IS_WINDOWS:
        for ttl in range(1, max_hops + 1):
            responder, rtt, status = _win_ttl_echo(ip, ttl, timeout)
            name = ""
            if responder:
                try:
                    name = socket.gethostbyaddr(responder)[0]
                except OSError:
                    name = ""
            hops.append({"ttl": ttl, "ip": responder, "host": name, "rtt_ms": rtt})
            emit(
                "toolbox",
                f"{ttl:>2}  "
                + (
                    f"{responder}" + (f" ({name})" if name else "") + f"  {fmt_ms(rtt)}" if responder else "*"
                ),
            )
            if status == 0 and responder == ip:
                break
    else:
        binary = "traceroute"
        args = [binary, "-n", "-q", "1", "-w", str(max(1, round(timeout))), "-m", str(max_hops), ip]
        try:
            out = subprocess.run(
                args, capture_output=True, text=True, timeout=max_hops * (timeout + 1) + 5
            ).stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DiagError(f"traceroute unavailable: {exc}") from exc
        for line in out.splitlines()[1:]:
            m = re.match(r"\s*(\d+)\s+(\S+)(?:\s+([\d.]+)\s*ms)?", line)
            if not m:
                continue
            responder = None if m.group(2) == "*" else m.group(2)
            hop = {
                "ttl": int(m.group(1)),
                "ip": responder,
                "host": "",
                "rtt_ms": float(m.group(3)) if m.group(3) else None,
            }
            hops.append(hop)
            emit("toolbox", line.strip())
    reached = any(h["ip"] == ip for h in hops)
    emit(
        "toolbox", f"traceroute {target}: {len(hops)} hops · {'reached' if reached else 'target not reached'}"
    )
    return {"target": target, "ip": ip, "hops": hops, "reached": reached}


# --------------------------------------------------------------------------- #
# DNS (minimal RFC 1035 client)
# --------------------------------------------------------------------------- #
QTYPES = {
    "A": 1,
    "NS": 2,
    "CNAME": 5,
    "SOA": 6,
    "PTR": 12,
    "MX": 15,
    "TXT": 16,
    "AAAA": 28,
    "SRV": 33,
    "CAA": 257,
}
_RCODES = {0: "NOERROR", 1: "FORMERR", 2: "SERVFAIL", 3: "NXDOMAIN", 4: "NOTIMP", 5: "REFUSED"}


def _encode_name(name: str) -> bytes:
    out = b""
    for label in name.rstrip(".").split("."):
        if label:
            out += bytes([len(label)]) + label.encode("idna")
    return out + b"\0"


def _read_name(data: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    jumped = False
    end = offset
    for _ in range(128):  # loop guard against malicious compression pointers
        length = data[offset]
        if length & 0xC0 == 0xC0:
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if not jumped:
                end = offset + 2
            offset, jumped = pointer, True
            continue
        if length == 0:
            if not jumped:
                end = offset + 1
            break
        labels.append(data[offset + 1 : offset + 1 + length].decode("utf-8", "replace"))
        offset += 1 + length
    return ".".join(labels) + ".", end


def _rdata(data: bytes, rtype: int, offset: int, length: int) -> str:
    raw = data[offset : offset + length]
    if rtype == 1 and length == 4:
        return socket.inet_ntoa(raw)
    if rtype == 28 and length == 16:
        return socket.inet_ntop(socket.AF_INET6, raw)
    if rtype in (2, 5, 12):
        return _read_name(data, offset)[0]
    if rtype == 15:
        return f"{struct.unpack('!H', raw[:2])[0]} {_read_name(data, offset + 2)[0]}"
    if rtype == 16:
        parts, i = [], 0
        while i < len(raw):
            n = raw[i]
            parts.append(raw[i + 1 : i + 1 + n].decode("utf-8", "replace"))
            i += 1 + n
        return " ".join(f'"{p}"' for p in parts)
    if rtype == 6:
        mname, o = _read_name(data, offset)
        rname, o = _read_name(data, o)
        serial, refresh, retry, expire, minimum = struct.unpack("!IIIII", data[o : o + 20])
        return f"{mname} {rname} serial={serial} refresh={refresh}s retry={retry}s expire={expire}s min={minimum}s"
    if rtype == 33:
        prio, weight, port = struct.unpack("!HHH", raw[:6])
        return f"{prio} {weight} {port} {_read_name(data, offset + 6)[0]}"
    return raw.hex()


def dns_query(name: str, qtype: str = "A", server: str = "1.1.1.1", timeout: float = 2.0) -> dict[str, Any]:
    qtype = qtype.upper()
    if qtype not in QTYPES:
        raise DiagError(f"Unsupported record type {qtype}; use one of {', '.join(QTYPES)}")
    if qtype == "PTR":
        with contextlib.suppress(ValueError):
            name = ipaddress.ip_address(name).reverse_pointer
    validate_target(name.rstrip(".") if not name.endswith(".arpa") else "x.arpa")
    try:
        ipaddress.ip_address(server)
    except ValueError as exc:
        raise DiagError(f"DNS server must be an IP address: {server!r}") from exc
    qid = random.randint(0, 0xFFFF)
    packet = (
        struct.pack("!HHHHHH", qid, 0x0100, 1, 0, 0, 0)
        + _encode_name(name)
        + struct.pack("!HH", QTYPES[qtype], 1)
    )
    family = socket.AF_INET6 if ":" in server else socket.AF_INET
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        start = time.perf_counter()
        try:
            sock.sendto(packet, (server, 53))
            while True:
                data, _ = sock.recvfrom(4096)
                if len(data) >= 12 and struct.unpack("!H", data[:2])[0] == qid:
                    break
        except OSError as exc:
            emit("toolbox", f"dig @{server} {name} {qtype}: no answer ({exc})", "warning")
            return {
                "name": name,
                "type": qtype,
                "server": server,
                "rcode": "TIMEOUT",
                "ms": None,
                "answers": [],
            }
        elapsed = round((time.perf_counter() - start) * 1000, 3)
    flags, qd, an = struct.unpack("!HHH", data[2:8])
    rcode = _RCODES.get(flags & 0x0F, str(flags & 0x0F))
    offset = 12
    for _ in range(qd):
        _, offset = _read_name(data, offset)
        offset += 4
    answers = []
    for _ in range(an):
        rname, offset = _read_name(data, offset)
        rtype, _rclass, ttl, rdlen = struct.unpack("!HHIH", data[offset : offset + 10])
        offset += 10
        type_name = next((k for k, v in QTYPES.items() if v == rtype), str(rtype))
        answers.append(
            {"name": rname, "type": type_name, "ttl_s": ttl, "data": _rdata(data, rtype, offset, rdlen)}
        )
        offset += rdlen
    emit(
        "toolbox",
        f"dig @{server} {name} {qtype} → {rcode} in {fmt_ms(elapsed)} · "
        + (", ".join(a["data"] for a in answers[:6]) or "no records")
        + (" (truncated)" if flags & 0x0200 else ""),
    )
    return {
        "name": name,
        "type": qtype,
        "server": server,
        "rcode": rcode,
        "ms": elapsed,
        "authoritative": bool(flags & 0x0400),
        "truncated": bool(flags & 0x0200),
        "answers": answers,
    }


def dns_benchmark(name: str, servers: list[str], qtype: str = "A", rounds: int = 3) -> dict[str, Any]:
    """Query the same name on several resolvers; median latency per resolver."""
    rounds = max(1, min(int(rounds), 10))
    out: list[dict[str, Any]] = []
    for server in servers[:10]:
        times = []
        last: dict[str, Any] = {}
        for _ in range(rounds):
            last = dns_query(name, qtype, server)
            if last["ms"] is not None:
                times.append(last["ms"])
        times.sort()
        out.append(
            {
                "server": server,
                "median_ms": times[len(times) // 2] if times else None,
                "min_ms": times[0] if times else None,
                "answered": len(times),
                "rounds": rounds,
                "rcode": last.get("rcode"),
                "answers": [a["data"] for a in last.get("answers", [])][:5],
            }
        )
    out.sort(key=lambda r: (r["median_ms"] is None, r["median_ms"] or 0))
    if out and out[0]["median_ms"] is not None:
        emit(
            "toolbox",
            f"fastest resolver for {name}: {out[0]['server']} ({fmt_ms(out[0]['median_ms'])} median)",
        )
    return {"name": name, "type": qtype, "results": out}


# --------------------------------------------------------------------------- #
# TCP / HTTP / TLS
# --------------------------------------------------------------------------- #
def tcp_check(target: str, port: int, count: int = 3, timeout: float = 2.0) -> dict[str, Any]:
    target = validate_target(target)
    if not 1 <= int(port) <= 65535:
        raise DiagError("port must be 1-65535")
    ip, _ = resolve(target)
    times: list[float | None] = []
    banner = ""
    for i in range(max(1, min(int(count), 20))):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            start = time.perf_counter()
            code = sock.connect_ex((ip, int(port)))
            elapsed = round((time.perf_counter() - start) * 1000, 3)
            if code == 0:
                times.append(elapsed)
                if i == 0:
                    try:
                        sock.settimeout(0.8)
                        banner = sock.recv(256).decode("utf-8", "replace").strip()
                    except OSError:
                        banner = ""
                emit(
                    "toolbox",
                    f"tcp {ip}:{port} connected in {fmt_ms(elapsed)}"
                    + (f" · banner “{banner[:80]}”" if banner and i == 0 else ""),
                )
            else:
                times.append(None)
                emit(
                    "toolbox",
                    f"tcp {ip}:{port} failed: {os.strerror(code) if code < 10000 else f'WSA error {code}'}",
                    "warning",
                )
    ok = [t for t in times if t is not None]
    return {
        "target": target,
        "ip": ip,
        "port": int(port),
        "open": bool(ok),
        "connect_ms": times,
        "avg_ms": round(fmean(ok), 3) if ok else None,
        "banner": banner,
    }


def _cert_summary(cert: dict[str, Any], der: bytes | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "subject": ", ".join("=".join(x) for rdn in cert.get("subject", ()) for x in rdn),
        "issuer": ", ".join("=".join(x) for rdn in cert.get("issuer", ()) for x in rdn),
        "san": [v for k, v in cert.get("subjectAltName", ()) if k in ("DNS", "IP Address")],
        "not_before": cert.get("notBefore"),
        "not_after": cert.get("notAfter"),
    }
    if der:
        try:
            from datetime import UTC, datetime

            from cryptography import x509
            from cryptography.hazmat.primitives.asymmetric import ec, rsa

            c = x509.load_der_x509_certificate(der)
            key = c.public_key()
            out["key"] = (
                f"RSA {key.key_size} bit"
                if isinstance(key, rsa.RSAPublicKey)
                else f"EC {key.curve.name}"
                if isinstance(key, ec.EllipticCurvePublicKey)
                else type(key).__name__
            )
            out["signature_algorithm"] = c.signature_hash_algorithm.name if c.signature_hash_algorithm else ""
            out["serial"] = format(c.serial_number, "x")
            out["days_remaining"] = (c.not_valid_after_utc - datetime.now(UTC)).days
            out["self_signed"] = c.issuer == c.subject
            if not out["subject"]:
                out["subject"] = c.subject.rfc4514_string()
                out["issuer"] = c.issuer.rfc4514_string()
            try:
                san = c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
                out["san"] = [str(v) for v in san.get_values_for_type(x509.DNSName)] + [
                    str(v) for v in san.get_values_for_type(x509.IPAddress)
                ]
            except x509.ExtensionNotFound:
                pass
            out["not_before"] = c.not_valid_before_utc.isoformat()
            out["not_after"] = c.not_valid_after_utc.isoformat()
        except Exception:
            pass
    return out


def tls_inspect(target: str, port: int = 443, timeout: float = 4.0) -> dict[str, Any]:
    target = validate_target(target)
    ip, _ = resolve(target)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_alpn_protocols(["h2", "http/1.1"])
    start = time.perf_counter()
    with socket.create_connection((ip, int(port)), timeout=timeout) as raw:
        connect_ms = round((time.perf_counter() - start) * 1000, 3)
        t1 = time.perf_counter()
        with ctx.wrap_socket(raw, server_hostname=target if not _is_ip(target) else None) as tls:
            handshake_ms = round((time.perf_counter() - t1) * 1000, 3)
            der = tls.getpeercert(binary_form=True)
            cipher = tls.cipher()
            version = tls.version()
            alpn = tls.selected_alpn_protocol()
    # Verify separately with the system trust store, to report trust status.
    trusted, trust_error = True, ""
    try:
        vctx = ssl.create_default_context()
        with (
            socket.create_connection((ip, int(port)), timeout=timeout) as raw2,
            vctx.wrap_socket(raw2, server_hostname=target),
        ):
            pass
    except ssl.SSLCertVerificationError as exc:
        trusted, trust_error = False, exc.verify_message or str(exc)
    except (OSError, ssl.SSLError) as exc:
        trusted, trust_error = False, str(exc)
    cert = _cert_summary({}, der)
    emit(
        "toolbox",
        f"tls {target}:{port} {version} · {cipher[0] if cipher else '?'} · ALPN {alpn or '-'} · "
        f"connect {fmt_ms(connect_ms)} · handshake {fmt_ms(handshake_ms)} · "
        f"{'trusted' if trusted else 'NOT trusted: ' + trust_error} · expires in {cert.get('days_remaining', '?')} d",
        "info" if trusted else "warning",
    )
    return {
        "target": target,
        "ip": ip,
        "port": int(port),
        "version": version,
        "cipher": cipher[0] if cipher else None,
        "cipher_bits": cipher[2] if cipher else None,
        "alpn": alpn,
        "connect_ms": connect_ms,
        "handshake_ms": handshake_ms,
        "trusted": trusted,
        "trust_error": trust_error,
        "certificate": cert,
    }


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def http_check(url: str, timeout: float = 8.0, max_bytes: int = 4 * 1024 * 1024) -> dict[str, Any]:
    """GET with a phase-by-phase timing breakdown (like curl -w)."""
    if "://" not in url:
        url = "http://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise DiagError("URL must be http:// or https:// with a host")
    host = validate_target(parts.hostname)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    t0 = time.perf_counter()
    ip, dns_ms = resolve(host)
    t_dns = time.perf_counter()
    sock = socket.create_connection((ip, port), timeout=timeout)
    t_connect = time.perf_counter()
    tls_ms = None
    tls_version = None
    try:
        if parts.scheme == "https":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(sock, server_hostname=host if not _is_ip(host) else None)
            tls_ms = round((time.perf_counter() - t_connect) * 1000, 3)
            tls_version = sock.version()
        t_req = time.perf_counter()
        request = (
            f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: NetScan-diag/1\r\n"
            "Accept: */*\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n"
        )
        sock.sendall(request.encode())
        first = sock.recv(65536)
        t_first = time.perf_counter()
        body = bytearray(first)
        while len(body) < max_bytes:
            chunk = sock.recv(65536)
            if not chunk:
                break
            body.extend(chunk)
        t_end = time.perf_counter()
    finally:
        sock.close()
    head, _, payload = bytes(body).partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1", "replace").split("\r\n")
    status_line = lines[0] if lines else ""
    m = re.match(r"HTTP/(\S+)\s+(\d{3})\s*(.*)", status_line)
    headers: dict[str, str] = {}
    for line in lines[1:]:
        k, _, v = line.partition(":")
        if k:
            headers[k.strip().lower()] = v.strip()
    transfer_s = t_end - t_first
    timing = {
        "dns_ms": dns_ms,
        "connect_ms": round((t_connect - t_dns) * 1000, 3),
        "tls_ms": tls_ms,
        "ttfb_ms": round((t_first - t_req) * 1000, 3),
        "transfer_ms": round(transfer_s * 1000, 3),
        "total_ms": round((t_end - t0) * 1000, 3),
    }
    size = len(payload)
    result = {
        "url": url,
        "ip": ip,
        "http_version": m.group(1) if m else None,
        "status": int(m.group(2)) if m else None,
        # No status line = not an HTTP/1.x answer: a captive portal, a
        # filtering proxy injecting a page, or a non-HTTP service.
        "reason": m.group(3) if m else f"no HTTP status line — non-HTTP response ({len(body)} bytes)",
        "headers": {
            k: headers[k]
            for k in (
                "server",
                "content-type",
                "content-length",
                "location",
                "strict-transport-security",
                "content-security-policy",
                "x-frame-options",
                "x-content-type-options",
                "cache-control",
                "set-cookie",
            )
            if k in headers
        },
        "body_bytes": size,
        "truncated": len(body) >= max_bytes,
        "tls_version": tls_version,
        "timing": timing,
        "throughput_mbps": round(size * 8 / transfer_s / 1_000_000, 2)
        if transfer_s > 0 and size > 262144
        else None,
        "security_headers_missing": [
            h
            for h in (
                "strict-transport-security",
                "content-security-policy",
                "x-frame-options",
                "x-content-type-options",
            )
            if h not in headers and (h != "strict-transport-security" or parts.scheme == "https")
        ],
    }
    emit(
        "toolbox",
        f"GET {url} → {result['status']} {result['reason']} · dns {fmt_ms(dns_ms)} · connect {fmt_ms(timing['connect_ms'])}"
        + (f" · tls {fmt_ms(tls_ms)}" if tls_ms is not None else "")
        + f" · ttfb {fmt_ms(timing['ttfb_ms'])} · transfer {fmt_ms(timing['transfer_ms'])} · total {fmt_ms(timing['total_ms'])}"
        + f" · {size / 1024:.1f} KiB",
    )
    return result


# --------------------------------------------------------------------------- #
# Pure calculators
# --------------------------------------------------------------------------- #
def subnet(cidr: str) -> dict[str, Any]:
    try:
        net = ipaddress.ip_network(cidr.strip(), strict=False)
    except ValueError as exc:
        raise DiagError(f"Invalid CIDR: {cidr!r}") from exc
    hosts = net.num_addresses - (2 if net.version == 4 and net.prefixlen < 31 else 0)
    out: dict[str, Any] = {
        "network": str(net.network_address),
        "prefix": net.prefixlen,
        "cidr": str(net),
        "netmask": str(net.netmask),
        "wildcard": str(net.hostmask),
        "broadcast": str(net.broadcast_address) if net.version == 4 else None,
        "addresses": net.num_addresses,
        "usable_hosts": max(hosts, 0),
        "first_host": str(net.network_address + (1 if net.prefixlen < 31 and net.version == 4 else 0)),
        "last_host": str(net.broadcast_address - (1 if net.prefixlen < 31 and net.version == 4 else 0)),
        "private": net.is_private,
        "version": net.version,
    }
    return out


def mac_lookup(mac: str) -> dict[str, Any]:
    from netscan.classify import mac_info
    from netscan.scanner.discovery import normalize_mac
    from netscan.scanner.enrich import get_vendor

    norm = normalize_mac(mac)
    if not re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", norm):
        raise DiagError(f"Invalid MAC: {mac!r}")
    info = mac_info(norm)
    return {"mac": norm, "vendor": get_vendor(norm), **info.as_dict()}
