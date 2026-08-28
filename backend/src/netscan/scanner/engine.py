"""Scan engine: orchestrates discovery + enrichment into a ScanResult.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import ipaddress
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from netscan.config import ScanDefaults
from netscan.models import Device, PortInfo, ScanResult, StageTiming
from netscan.scanner import discovery, enrich, mdns, speed, tools
from netscan.scanner.fingerprint import fingerprint_http

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, int, int], None]

# Stages that can be launched individually (``only=`` on run_scan / POST
# /api/scans) instead of the bundled quick/full pipeline.
ONLY_STAGES = {"arp", "mdns", "nmap", "rustscan", "nuclei"}


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
        mdns_services=list(mdns_map.get(raw["ip"], {}).get("services", []) or []),  # type: ignore[call-overload]
    )
    dev.hostname = enrich.resolve_hostname(dev.ip)
    dev.latency_ms = enrich.ping_host(dev.ip, cfg.ping_timeout)

    if ports_to_scan:
        # RustScan pipeline: ultra-fast full-range discovery, then nmap -sV.
        # Falls back to the built-in threaded socket scan when unavailable.
        rustscan_ports: list[int] = []
        if cfg.use_rustscan and caps.tools.get("rustscan"):
            rustscan_ports = tools.rustscan_ports(dev.ip)
        if rustscan_ports:
            dev.open_ports = [
                PortInfo(port=p, service=ports_to_scan.get(p, "unknown")) for p in sorted(rustscan_ports)
            ]
        else:
            dev.open_ports = enrich.scan_ports(dev.ip, ports_to_scan, cfg.workers, cfg.port_timeout)
        if cfg.use_nmap and caps.tools.get("nmap") and dev.open_ports:
            versions = tools.nmap_service_scan(dev.ip, [p.port for p in dev.open_ports])
            for port_info in dev.open_ports:
                if port_info.port in versions:
                    port_info.version = versions[port_info.port]
            if cfg.use_nmap_os:
                os_guess = tools.nmap_os_scan(dev.ip)
                if os_guess:
                    dev.os_guess = os_guess
        if not dev.os_guess:
            dev.os_guess = enrich.detect_os_from_ports(dev.open_ports)

    if cfg.use_fingerprint and dev.open_ports:
        dev.http = fingerprint_http(dev.ip, dev.open_ports)

    if cfg.use_speedtest:
        dev.metrics = speed.measure_device(
            dev.ip,
            dev.open_ports,
            count=cfg.speedtest_pings,
            ping_timeout=cfg.ping_timeout,
            throughput=cfg.use_throughput,
        )
        dev.metrics.measured_at = datetime.now()
        # Prefer the averaged latency over the single-shot ping value.
        if dev.metrics.latency_avg_ms is not None:
            dev.latency_ms = dev.metrics.latency_avg_ms
    return dev


def run_scan(
    cfg: ScanDefaults | None = None,
    network: str | None = None,
    full: bool | None = None,
    only: str | None = None,
    progress: ProgressFn | None = None,
) -> ScanResult:
    """Execute a scan and return the aggregated result.

    ``only``, when set, restricts the run to a single tool/stage — one of
    ``ONLY_STAGES`` — instead of the bundled quick/full pipeline. An ARP
    sweep still always runs first so the full current device set is known
    (online/offline bookkeeping and new-device alerts stay correct); only
    the optional enrichment stages are narrowed to the requested one.
    """
    cfg = cfg or ScanDefaults()
    if only is not None and only not in ONLY_STAGES:
        raise ValueError(f"unknown scan stage: {only!r}")
    caps = tools.Capabilities.detect()
    start = time.perf_counter()

    timings: list[StageTiming] = []

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
    _t0 = time.perf_counter()
    scan_iface = iface if iface not in ("", "default", "custom") else None
    raw_devices = discovery.arp_scan(network_cidr, iface=scan_iface)
    timings.append(StageTiming(stage="arp", duration_s=round(time.perf_counter() - _t0, 2)))
    emit("arp", 1, 1)

    use_full = cfg.full if full is None else full
    if only in ("nmap", "rustscan"):
        use_full = True  # an explicit single-tool run should be thorough

    needs_ports = only is None or only in ("nmap", "rustscan", "nuclei")
    if not needs_ports:
        ports_to_scan: dict[int, str] = {}
    elif only == "nuclei":
        # nuclei only needs to know which ports are web UIs, not their versions.
        ports_to_scan = dict(enrich.COMMON_PORTS)
    else:
        ports_to_scan = {**enrich.COMMON_PORTS, **enrich.EXTENDED_PORTS} if use_full else enrich.COMMON_PORTS

    if only is not None:
        cfg = cfg.model_copy(
            update={
                "use_mdns": only == "mdns",
                "use_nmap": only == "nmap",
                "use_rustscan": only == "rustscan",
                "use_nuclei": only == "nuclei",
                "use_fingerprint": only == "nuclei",  # nuclei needs dev.http URLs
                "use_speedtest": False,
            }
        )

    # Main-thread, non-thread-safe steps first
    vendor_cache = enrich.resolve_vendors([d["mac"] for d in raw_devices])
    mdns_map: dict[str, dict[str, object]] = {}
    if cfg.use_mdns and caps.mdns:
        emit("mdns", 0, 1)
        _t0 = time.perf_counter()
        mdns_map = mdns.mdns_discover()
        timings.append(StageTiming(stage="mdns", duration_s=round(time.perf_counter() - _t0, 2)))
        emit("mdns", 1, 1)

    devices: list[Device] = []
    total = len(raw_devices)
    emit("enrich", 0, total)
    _t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=min(cfg.workers, max(total, 1))) as executor:
        futures = {
            executor.submit(_enrich_device, raw, ports_to_scan, vendor_cache, mdns_map, cfg, caps): raw
            for raw in raw_devices
        }
        for i, future in enumerate(as_completed(futures), 1):
            try:
                devices.append(future.result())
            except Exception:
                # A single host must not sink the whole scan.
                logger.exception("Error enriqueciendo %s", futures[future].get("ip", "?"))
            emit("enrich", i, total)
    timings.append(StageTiming(stage="enrich", duration_s=round(time.perf_counter() - _t0, 2)))

    devices.sort(key=lambda d: ipaddress.IPv4Address(d.ip))

    # Vulnerability pass over discovered web UIs (opt-in, needs nuclei).
    # Capped: nuclei is slow and noisy, so never feed it an unbounded list.
    vulnerabilities: list[dict[str, str]] = []
    if cfg.use_nuclei and caps.tools.get("nuclei"):
        urls = [http.url for dev in devices for http in dev.http][: cfg.nuclei_max_targets]
        emit("nuclei", 0, 1)
        _t0 = time.perf_counter()
        vulnerabilities = tools.nuclei_scan(urls)
        timings.append(StageTiming(stage="nuclei", duration_s=round(time.perf_counter() - _t0, 2)))
        emit("nuclei", 1, 1)

    ports_open_total = sum(len(d.open_ports) for d in devices)

    return ScanResult(
        network=network_cidr,
        interface=iface,
        local_ip=local_ip,
        total_devices=len(devices),
        duration_s=round(time.perf_counter() - start, 2),
        devices=devices,
        vulnerabilities=vulnerabilities,
        capabilities=caps.as_dict(),
        stage_timings=timings,
        ports_open_total=ports_open_total,
        link_speed_mbps=speed.local_link_speed_mbps(),
        speedtest_ran=cfg.use_speedtest,
    )
