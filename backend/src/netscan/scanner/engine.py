"""Scan engine: orchestrates discovery + enrichment into a ScanResult.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from netscan.config import ScanDefaults
from netscan.models import Device, ScanResult
from netscan.scanner import discovery, enrich, mdns, tools
from netscan.scanner.fingerprint import fingerprint_http

ProgressFn = Callable[[str, int, int], None]


def _enrich_device(
    raw: dict[str, str],
    ports_to_scan: dict[int, str],
    vendor_cache: dict[str, str],
    mdns_map: dict[str, dict[str, object]],
    cfg: ScanDefaults,
    caps: tools.Capabilities,
) -> Device:
    dev = Device(
        ip=raw["ip"],
        mac=raw.get("mac", ""),
        vendor=vendor_cache.get(raw.get("mac", ""), ""),
        mdns_name=str(mdns_map.get(raw["ip"], {}).get("name", "")),
        mdns_services=list(mdns_map.get(raw["ip"], {}).get("services", [])),  # type: ignore[arg-type]
    )
    dev.hostname = enrich.resolve_hostname(dev.ip)
    dev.latency_ms = enrich.ping_host(dev.ip, cfg.ping_timeout)

    if ports_to_scan:
        dev.open_ports = enrich.scan_ports(dev.ip, ports_to_scan, cfg.workers, cfg.port_timeout)
        if cfg.use_nmap and caps.tools.get("nmap"):
            versions = tools.nmap_service_scan(dev.ip, [p.port for p in dev.open_ports])
            for port_info in dev.open_ports:
                if port_info.port in versions:
                    port_info.version = versions[port_info.port]
        dev.os_guess = enrich.detect_os_from_ports(dev.open_ports)

    if cfg.use_fingerprint and dev.open_ports:
        dev.http = fingerprint_http(dev.ip, dev.open_ports)
    return dev


def run_scan(
    cfg: ScanDefaults | None = None,
    network: str | None = None,
    full: bool | None = None,
    progress: ProgressFn | None = None,
) -> ScanResult:
    """Execute a full scan and return the aggregated result."""
    cfg = cfg or ScanDefaults()
    caps = tools.Capabilities.detect()
    start = time.perf_counter()

    def emit(stage: str, done: int, total: int) -> None:
        if progress:
            progress(stage, done, total)

    network_cidr = network or cfg.network
    if network_cidr:
        local_ip, iface = "", "custom"
        ipaddress.IPv4Network(network_cidr, strict=False)  # validate
    else:
        network_cidr, local_ip, iface = discovery.get_local_network()

    emit("arp", 0, 1)
    raw_devices = discovery.arp_scan(network_cidr)
    emit("arp", 1, 1)

    use_full = cfg.full if full is None else full
    ports_to_scan = {**enrich.COMMON_PORTS, **enrich.EXTENDED_PORTS} if use_full else enrich.COMMON_PORTS

    # Main-thread, non-thread-safe steps first
    vendor_cache = enrich.resolve_vendors([d["mac"] for d in raw_devices])
    mdns_map: dict[str, dict[str, object]] = {}
    if cfg.use_mdns and caps.mdns:
        emit("mdns", 0, 1)
        mdns_map = mdns.mdns_discover()
        emit("mdns", 1, 1)

    devices: list[Device] = []
    total = len(raw_devices)
    with ThreadPoolExecutor(max_workers=min(cfg.workers, max(total, 1))) as executor:
        futures = {
            executor.submit(_enrich_device, raw, ports_to_scan, vendor_cache, mdns_map, cfg, caps): raw
            for raw in raw_devices
        }
        for i, future in enumerate(as_completed(futures), 1):
            devices.append(future.result())
            emit("enrich", i, total)

    devices.sort(key=lambda d: ipaddress.IPv4Address(d.ip))
    return ScanResult(
        network=network_cidr,
        interface=iface,
        local_ip=local_ip,
        total_devices=len(devices),
        duration_s=round(time.perf_counter() - start, 2),
        devices=devices,
        capabilities=caps.as_dict(),
    )
