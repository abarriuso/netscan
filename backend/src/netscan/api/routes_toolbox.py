"""Diagnostics toolbox endpoints (see netscan.diag).

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

These run on the NetScan host — they answer "what does the network look
like *from here*". Single-target probes (ping, traceroute, DNS, one TCP
port, one HTTP/TLS endpoint) may point anywhere, like any looking-glass;
multi-port scans stay restricted to private ranges (see /api/scans).
"""

from __future__ import annotations

import ipaddress
import ssl
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from netscan import diag
from netscan.api.deps import get_state
from netscan.events import emit
from netscan.scanner import enrich

router = APIRouter(prefix="/api/tools")


class TargetRequest(BaseModel):
    target: str = Field(min_length=1, max_length=253)
    count: int = Field(default=5, ge=1, le=50)
    timeout_ms: int = Field(default=1000, ge=100, le=10000)


class TraceRequest(BaseModel):
    target: str = Field(min_length=1, max_length=253)
    max_hops: int = Field(default=20, ge=1, le=30)
    timeout_ms: int = Field(default=1000, ge=100, le=5000)


class DnsRequest(BaseModel):
    name: str = Field(min_length=1, max_length=253)
    type: str = "A"
    server: str = "1.1.1.1"


class DnsBenchRequest(BaseModel):
    name: str = Field(default="example.com", min_length=1, max_length=253)
    type: str = "A"
    servers: list[str] = Field(default_factory=list, max_length=10)
    rounds: int = Field(default=3, ge=1, le=10)


class TcpRequest(BaseModel):
    target: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    count: int = Field(default=3, ge=1, le=20)


class PortScanRequest(BaseModel):
    target: str
    ports: str = Field(default="", description="e.g. '22,80,443,8000-8100'; empty = common + extended")
    timeout_ms: int = Field(default=500, ge=50, le=5000)


class HttpRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class TlsRequest(BaseModel):
    target: str = Field(min_length=1, max_length=253)
    port: int = Field(default=443, ge=1, le=65535)


class SubnetRequest(BaseModel):
    cidr: str


class MacRequest(BaseModel):
    mac: str


def _run(name: str, fn, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except diag.DiagError as exc:
        emit("toolbox", f"{name}: {exc}", "warning")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        reason = _explain(exc)
        emit("toolbox", f"{name} failed: {reason}", "warning")
        raise HTTPException(status_code=502, detail=f"{name} failed: {reason}") from exc


def _explain(exc: OSError) -> str:
    """Network errors in words, not WinError numbers."""
    if isinstance(exc, ConnectionResetError):
        return (
            "connection reset by the remote side (TCP RST) — a firewall, proxy or filter "
            "on the path, or the server refusing this client"
        )
    if isinstance(exc, ConnectionRefusedError):
        return "connection refused — nothing listens on that port (TCP RST to the SYN)"
    if isinstance(exc, TimeoutError):
        return "timed out — host down, port filtered (SYN dropped) or path blocked"
    if isinstance(exc, ssl.SSLError):
        return f"TLS error: {exc.reason or exc}"
    return str(exc)


@router.post("/ping")
def ping(req: TargetRequest) -> dict[str, Any]:
    return _run("ping", diag.ping, req.target, req.count, req.timeout_ms / 1000)


@router.post("/traceroute")
def traceroute(req: TraceRequest) -> dict[str, Any]:
    return _run("traceroute", diag.traceroute, req.target, req.max_hops, req.timeout_ms / 1000)


@router.post("/dns")
def dns(req: DnsRequest) -> dict[str, Any]:
    return _run("dns", diag.dns_query, req.name, req.type, req.server)


@router.post("/dns-bench")
def dns_bench(req: DnsBenchRequest) -> dict[str, Any]:
    """Time the same query on several resolvers. Defaults to the gateway,
    every configured AdGuard/Pi-hole and the big public resolvers."""
    state = get_state()
    servers = list(req.servers)
    if not servers:
        if state.gateway_ip:
            servers.append(state.gateway_ip)
        for inst in [*state.settings.adguard, *state.settings.pihole]:
            host = getattr(inst, "host", "")
            try:
                ipaddress.ip_address(host)
                servers.append(host)
            except ValueError:
                continue
        servers += ["1.1.1.1", "8.8.8.8", "9.9.9.9"]
    servers = list(dict.fromkeys(servers))
    return _run("dns-bench", diag.dns_benchmark, req.name, servers, req.type, req.rounds)


@router.post("/tcp")
def tcp(req: TcpRequest) -> dict[str, Any]:
    return _run("tcp", diag.tcp_check, req.target, req.port, req.count)


def _parse_ports(spec: str) -> dict[int, str]:
    if not spec.strip():
        return {**enrich.COMMON_PORTS, **enrich.EXTENDED_PORTS}
    ports: dict[int, str] = {}
    known = {**enrich.COMMON_PORTS, **enrich.EXTENDED_PORTS}
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                lo, hi = (int(x) for x in part.split("-", 1))
                rng = range(lo, hi + 1)
            else:
                rng = range(int(part), int(part) + 1)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Bad port spec: {part!r}") from exc
        for p in rng:
            if not 1 <= p <= 65535:
                raise HTTPException(status_code=400, detail=f"Port out of range: {p}")
            ports[p] = known.get(p, "unknown")
    if len(ports) > 4096:
        raise HTTPException(status_code=400, detail="At most 4096 ports per request")
    return ports


@router.post("/portscan")
def portscan(req: PortScanRequest) -> dict[str, Any]:
    """TCP connect scan of one host. Private addresses only (no scan oracle)."""
    try:
        ip = ipaddress.IPv4Address(req.target.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="target must be an IPv4 address") from exc
    if not ip.is_private:
        raise HTTPException(status_code=400, detail="Port scans are limited to private addresses (RFC 1918)")
    ports = _parse_ports(req.ports)
    open_ports = enrich.scan_ports(str(ip), ports, max_workers=64, timeout=req.timeout_ms / 1000)
    return {"target": str(ip), "scanned": len(ports), "open": [p.model_dump() for p in open_ports]}


@router.post("/http")
def http(req: HttpRequest) -> dict[str, Any]:
    return _run("http", diag.http_check, req.url)


@router.post("/tls")
def tls(req: TlsRequest) -> dict[str, Any]:
    return _run("tls", diag.tls_inspect, req.target, req.port)


@router.post("/subnet")
def subnet(req: SubnetRequest) -> dict[str, Any]:
    return _run("subnet", diag.subnet, req.cidr)


@router.post("/mac")
def mac(req: MacRequest) -> dict[str, Any]:
    return _run("mac", diag.mac_lookup, req.mac)
