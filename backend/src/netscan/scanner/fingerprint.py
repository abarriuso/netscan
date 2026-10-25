"""HTTP/TLS fingerprinting of discovered web UIs.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Captures page title, Server header and TLS certificate details (issuer,
expiry, self-signed) for every HTTP(S) port found — useful for spotting
expired or untrusted certs in a homelab.
"""

from __future__ import annotations

import contextlib
import re
import socket
import ssl
import time
from datetime import UTC, datetime

import httpx
from cryptography import x509

from netscan.events import emit, fmt_ms
from netscan.models import HttpInfo, PortInfo, TlsInfo


def _lenient_ctx() -> ssl.SSLContext:
    """TLS client context that talks to anything — including the legacy
    TLS 1.0/1.1 and weak ciphers of old routers/NAS/printers, which OpenSSL 3
    refuses by default. Detecting those is the point of a security scanner;
    nothing is trusted or verified with this context."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
    with contextlib.suppress(ssl.SSLError):
        ctx.set_ciphers("ALL:@SECLEVEL=0")
    with contextlib.suppress(ValueError, ssl.SSLError):
        ctx.minimum_version = ssl.TLSVersion.TLSv1
    return ctx


def _tls_reason(exc: BaseException) -> str:
    text = str(exc)
    if "UNRECOGNIZED_NAME" in text:
        return "TLS: server requires SNI (name-based virtual host / reverse proxy)"
    if "HANDSHAKE_FAILURE" in text or "NO_PROTOCOLS" in text or "UNSUPPORTED_PROTOCOL" in text:
        return "TLS handshake rejected (no cipher/protocol in common)"
    if "WRONG_VERSION_NUMBER" in text or "record layer failure" in text:
        return "not TLS on this port"
    return f"{type(exc).__name__}: {text[:120]}"


HTTP_PORTS = {
    80,
    81,
    443,
    3000,
    5000,
    5001,
    8000,
    8006,
    8080,
    8081,
    8096,
    8123,
    8443,
    8888,
    9000,
    9090,
    9200,
    9443,
    32400,
}
# Ports that speak TLS from the first byte. Anything else in HTTP_PORTS is
# probed with a TLS handshake first (9090 Cockpit, 9443 Portainer... are
# HTTPS on non-standard ports) and falls back to plain HTTP.
TLS_PORTS = {443, 5001, 8006, 8443, 9443}
_TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _name_part(name: x509.Name, oid: x509.ObjectIdentifier) -> str:
    attrs = name.get_attributes_for_oid(oid)
    if not attrs:
        return ""
    value = attrs[0].value
    return value if isinstance(value, str) else value.decode("utf-8", "replace")


def probe_tls(host: str, port: int, timeout: float = 4.0) -> TlsInfo | None:
    """Grab and decode the peer certificate, tolerating self-signed certs."""
    ctx = _lenient_ctx()
    try:
        with (
            socket.create_connection((host, port), timeout=timeout) as raw,
            ctx.wrap_socket(raw, server_hostname=host) as tls,
        ):
            der = tls.getpeercert(binary_form=True)
            version = tls.version() or ""
    except (OSError, ssl.SSLError) as exc:
        emit("tls", f"{host}:{port} handshake failed — {_tls_reason(exc)}", host=host, port=port)
        return None
    if der is None:
        emit(
            "tls",
            f"{host}:{port} {version or 'TLS'} handshake ok · no certificate presented",
            host=host,
            port=port,
        )
        return TlsInfo(version=version)

    info = TlsInfo(version=version)
    try:
        cert = x509.load_der_x509_certificate(der)
        info.issuer = ", ".join(
            part
            for part in (
                _name_part(cert.issuer, x509.NameOID.COMMON_NAME),
                _name_part(cert.issuer, x509.NameOID.ORGANIZATION_NAME),
            )
            if part
        )
        info.subject = ", ".join(
            part
            for part in (
                _name_part(cert.subject, x509.NameOID.COMMON_NAME),
                _name_part(cert.subject, x509.NameOID.ORGANIZATION_NAME),
            )
            if part
        )
        not_before = cert.not_valid_before_utc
        not_after = cert.not_valid_after_utc
        info.not_before = not_before.isoformat()
        info.not_after = not_after.isoformat()
        info.days_remaining = (not_after - datetime.now(UTC)).days
        info.self_signed = cert.issuer == cert.subject
    except ValueError:
        pass  # unparsable cert: keep whatever we already have
    expiry = (
        f"expires in {info.days_remaining} d"
        if (info.days_remaining or 0) >= 0
        else f"EXPIRED {-(info.days_remaining or 0)} d ago"
    )
    emit(
        "tls",
        f"{host}:{port} {info.version} · subject {info.subject or '?'} · issuer {info.issuer or '?'} · {expiry}"
        + (" · self-signed" if info.self_signed else ""),
        "warning"
        if (info.days_remaining is not None and info.days_remaining < 14)
        or info.version in ("TLSv1", "TLSv1.1")
        else "info",
        host=host,
        port=port,
        days_remaining=info.days_remaining,
        version=info.version,
    )
    return info


def _speaks_tls(ip: str, port: int, timeout: float) -> bool:
    ctx = _lenient_ctx()
    try:
        with (
            socket.create_connection((ip, port), timeout=timeout) as raw,
            ctx.wrap_socket(raw, server_hostname=ip),
        ):
            return True
    except ssl.SSLError as exc:
        # The server spoke TLS but refused us (SNI, ciphers): still HTTPS.
        return "UNRECOGNIZED_NAME" in str(exc) or "HANDSHAKE_FAILURE" in str(exc)
    except OSError:
        return False


def probe_http(ip: str, port: int, timeout: float = 4.0) -> HttpInfo | None:
    """Fetch status, headers and title from an HTTP(S) service.

    If following redirects fails (a typical router redirects :80 to an
    HTTPS UI with a legacy or SNI-only TLS setup), the first hop is
    recorded instead of losing the whole service.
    """
    tls = port in TLS_PORTS or (port not in (80, 81, 8080) and _speaks_tls(ip, port, min(timeout, 2.0)))
    scheme = "https" if tls else "http"
    url = f"{scheme}://{ip}:{port}/"
    info = HttpInfo(url=url)
    start = time.perf_counter()
    verify = _lenient_ctx()
    try:
        with httpx.Client(verify=verify, follow_redirects=True, timeout=timeout) as client:
            resp = client.get(url)
        _fill(info, resp)
        hops = len(resp.history)
        if hops:
            info.final_url = str(resp.url)
        plural = "s" if hops > 1 else ""
        emit(
            "http",
            f"GET {url} → {resp.status_code}"
            + (f" (after {hops} redirect{plural} → {resp.url})" if hops else "")
            + f" · {fmt_ms((time.perf_counter() - start) * 1000)} · {len(resp.content) / 1024:.1f} KiB"
            + (f" · server {info.server}" if info.server else "")
            + (f" · “{info.title}”" if info.title else ""),
            host=ip,
            port=port,
            status=resp.status_code,
        )
    except httpx.HTTPError as exc:
        reason = _tls_reason(exc) if "SSL" in str(exc) else f"{type(exc).__name__}: {exc}"
        try:
            with httpx.Client(verify=verify, follow_redirects=False, timeout=timeout) as client:
                resp = client.get(url)
            _fill(info, resp)
            location = resp.headers.get("location", "")
            info.error = f"redirect target failed ({reason})" if location else reason
            info.final_url = location
            emit(
                "http",
                f"GET {url} → {resp.status_code}"
                + (f" → {location}" if location else "")
                + f" · following it failed: {reason}",
                host=ip,
                port=port,
                status=resp.status_code,
            )
        except httpx.HTTPError as exc2:
            info.error = _tls_reason(exc2) if "SSL" in str(exc2) else f"{type(exc2).__name__}: {exc2}"
            emit("http", f"GET {url} failed: {info.error}", host=ip, port=port)
    if tls:
        info.tls = probe_tls(ip, port, timeout)
    return info


def _fill(info: HttpInfo, resp: httpx.Response) -> None:
    info.status_code = resp.status_code
    info.server = resp.headers.get("server", "")
    match = _TITLE_RE.search(resp.content[:65536])
    if match:
        info.title = re.sub(r"\s+", " ", match.group(1).decode("utf-8", "replace")).strip()[:120]


def fingerprint_http(ip: str, open_ports: list[PortInfo], timeout: float = 4.0) -> list[HttpInfo]:
    results: list[HttpInfo] = []
    for p in open_ports:
        if p.port in HTTP_PORTS:
            info = probe_http(ip, p.port, timeout)
            if info:
                results.append(info)
    return results
