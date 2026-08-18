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

from netscan.models import HttpInfo, PortInfo, TlsInfo

HTTP_PORTS = {80, 443, 8006, 8080, 8443, 8888, 9000, 9090, 32400, 8096}
TLS_PORTS = {443, 8006, 8443}
_TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


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
        # CERT_NONE hides getpeercert() dict; decode the DER manually
        # with a throwaway verified context trick: parse via ssl's internal
        # decoder against a PEM re-encode.
        pem = ssl.DER_cert_to_PEM_cert(der)
        decoded = ssl._ssl._test_decode_cert(  # type: ignore[attr-defined]
            _write_temp_pem(pem)
        )
        info.issuer = _name_to_str(decoded.get("issuer", ()))
        info.subject = _name_to_str(decoded.get("subject", ()))
        info.not_before = decoded.get("notBefore", "")
        info.not_after = decoded.get("notAfter", "")
        if info.not_after:
            expiry = datetime.strptime(info.not_after, "%b %d %H:%M:%S %Y %Z")
            expiry = expiry.replace(tzinfo=UTC)
            info.days_remaining = (expiry - datetime.now(UTC)).days
        info.self_signed = bool(info.issuer) and info.issuer == info.subject
    except Exception:
        pass
    return info


def _write_temp_pem(pem: str) -> str:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as fh:
        fh.write(pem)
        return fh.name


def _name_to_str(name: tuple) -> str:
    parts = []
    for rdn in name:
        for key, value in rdn:
            if key in ("commonName", "organizationName"):
                parts.append(str(value))
    return ", ".join(dict.fromkeys(parts))


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
