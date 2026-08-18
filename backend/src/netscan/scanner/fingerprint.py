"""HTTP/TLS fingerprinting of discovered web UIs.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Captures page title, Server header and TLS certificate details (issuer,
expiry, self-signed) for every HTTP(S) port found — useful for spotting
expired or untrusted certs in a homelab.
"""

from __future__ import annotations

import re
import socket
import ssl
from datetime import UTC, datetime

import httpx
from cryptography import x509

from netscan.models import HttpInfo, PortInfo, TlsInfo

HTTP_PORTS = {80, 443, 8006, 8080, 8443, 8888, 9000, 9090, 32400, 8096}
TLS_PORTS = {443, 8006, 8443}
_TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _name_part(name: x509.Name, oid: x509.ObjectIdentifier) -> str:
    attrs = name.get_attributes_for_oid(oid)
    if not attrs:
        return ""
    value = attrs[0].value
    return value if isinstance(value, str) else value.decode("utf-8", "replace")


def probe_tls(host: str, port: int, timeout: float = 4.0) -> TlsInfo | None:
    """Grab and decode the peer certificate, tolerating self-signed certs."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
    try:
        with (
            socket.create_connection((host, port), timeout=timeout) as raw,
            ctx.wrap_socket(raw, server_hostname=host) as tls,
        ):
            der = tls.getpeercert(binary_form=True)
            version = tls.version() or ""
    except (OSError, ssl.SSLError):
        return None
    if der is None:
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
    return info


def probe_http(ip: str, port: int, timeout: float = 4.0) -> HttpInfo | None:
    """Fetch headers + title from an HTTP(S) service."""
    scheme = "https" if port in TLS_PORTS else "http"
    url = f"{scheme}://{ip}:{port}/"
    info = HttpInfo(url=url)
    try:
        with httpx.Client(verify=False, follow_redirects=True, timeout=timeout) as client:
            resp = client.get(url)
        info.status_code = resp.status_code
        info.server = resp.headers.get("server", "")
        match = _TITLE_RE.search(resp.content[:65536])
        if match:
            info.title = match.group(1).decode("utf-8", "replace").strip()[:120]
    except httpx.HTTPError:
        if info.status_code == 0:
            return None
    if port in TLS_PORTS:
        info.tls = probe_tls(ip, port, timeout)
    return info


def fingerprint_http(ip: str, open_ports: list[PortInfo], timeout: float = 4.0) -> list[HttpInfo]:
    results: list[HttpInfo] = []
    for p in open_ports:
        if p.port in HTTP_PORTS:
            info = probe_http(ip, p.port, timeout)
            if info:
                results.append(info)
    return results
