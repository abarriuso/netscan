"""Scan engine: orchestrates discovery + enrichment into a ScanResult.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Every stage reports to two channels: the coarse ``progress(stage, done,
total)`` callback (CLI progress bar, header progress over /ws/progress) and
the fine-grained event bus (one event per host, port, request, command —
the dashboard terminal). A stage that does not run says why, instead of
silently not happening.
"""

from __future__ import annotations

import ipaddress
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlsplit

from netscan.config import ScanDefaults
from netscan.events import emit, fmt_ms, fmt_s
from netscan.models import Device, PortInfo, ScanResult, StageTiming
from netscan.scanner import discovery, enrich, mdns, speed, tools
from netscan.scanner.fingerprint import fingerprint_http

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, int, int], None]

# Stages that can be launched individually (``only=`` on run_scan / POST
# /api/scans) instead of the bundled quick/full pipeline.
ONLY_STAGES = {"arp", "mdns", "nmap", "rustscan", "nuclei", "whatweb", "testssl"}

# Stages that need dev.http populated (open ports + HTTP/TLS fingerprint)
# to have anything to work against.
_WEB_STAGES = {"nuclei", "whatweb", "testssl"}

# A reverse lookup with no PTR record can block ~5 s (Windows falls back to
# NetBIOS). It runs in parallel with the probes and is only waited for this
# much longer once they are done.
_PTR_GRACE_S = 1.5


def _in_background(fn, *args) -> tuple[threading.Thread, dict[str, object]]:
    box: dict[str, object] = {}

    def run() -> None:
        try:
            box["value"] = fn(*args)
        except Exception as exc:
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, box


def _enrich_device(
    raw: dict[str, str],
    ports_to_scan: dict[int, str],
    vendor_cache: dict[str, str],
    mdns_map: dict[str, dict[str, object]],
    cfg: ScanDefaults,
    caps: tools.Capabilities,
) -> Device:
    started = time.perf_counter()
    dev = Device(
        ip=raw["ip"],
        mac=raw.get("mac", ""),
        vendor=vendor_cache.get(raw.get("mac", ""), ""),
        mdns_name=str(mdns_map.get(raw["ip"], {}).get("name", "")),
        mdns_services=list(mdns_map.get(raw["ip"], {}).get("services", []) or []),  # type: ignore[call-overload]
        conflict_macs=[m for m in raw.get("conflict", "").split(",") if m],
    )
    emit(
        "scan",
        f"▶ {dev.ip} · {dev.mac or 'no MAC (off-link)'}" + (f" · {dev.vendor}" if dev.vendor else ""),
        "debug",
        host=dev.ip,
    )
    ptr_thread, ptr_box = _in_background(enrich.resolve_hostname, dev.ip)
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
    ptr_thread.join(timeout=_PTR_GRACE_S)
    if ptr_thread.is_alive():
        emit(
            "dns",
            f"PTR {dev.ip}: no answer within the grace period — hostname left empty",
            "debug",
            host=dev.ip,
        )
    elif "error" in ptr_box:
        raise ptr_box["error"]  # type: ignore[misc]
    else:
        dev.hostname = str(ptr_box.get("value") or "")
    emit(
        "scan",
        f"✓ {dev.ip} {dev.hostname or dev.mdns_name or ''} · RTT {fmt_ms(dev.latency_ms)} · "
        f"{len(dev.open_ports)} open ports · {len(dev.http)} web UIs · {fmt_s(time.perf_counter() - started)}",
        host=dev.ip,
    )
    return dev


def _plan(
    cfg: ScanDefaults, caps: tools.Capabilities, only: str | None, use_full: bool
) -> tuple[ScanDefaults, list[str]]:
    """Resolve which optional stages run, and the reason for each one that does not."""
    if only is not None:
        cfg = cfg.model_copy(
            update={
                "use_mdns": only == "mdns",
                "use_nmap": only == "nmap",
                "use_rustscan": only == "rustscan",
                "use_nuclei": only == "nuclei",
                "use_whatweb": only == "whatweb",
                "use_testssl": only == "testssl",
                "use_fingerprint": only in _WEB_STAGES,  # these need dev.http URLs
                "use_speedtest": False,
            }
        )
    elif use_full:
        # "Full" means every installed tool runs — the web audits are opt-in
        # only for the quick/scheduled scans because they are slow and loud.
        cfg = cfg.model_copy(
            update={
                "use_nuclei": cfg.use_nuclei or bool(caps.tools.get("nuclei")),
                "use_whatweb": cfg.use_whatweb or bool(caps.tools.get("whatweb")),
                "use_testssl": cfg.use_testssl or bool(caps.tools.get("testssl")),
            }
        )
    skipped: list[str] = []
    checks = (
        ("mdns", cfg.use_mdns, caps.mdns, "zeroconf not installed"),
        (
            "rustscan",
            cfg.use_rustscan,
            caps.tools.get("rustscan"),
            "not installed — built-in TCP connect scan used",
        ),
        ("nmap -sV", cfg.use_nmap, caps.tools.get("nmap"), "not installed — no service versions"),
        ("nuclei", cfg.use_nuclei, caps.tools.get("nuclei"), "not installed"),
        ("whatweb", cfg.use_whatweb, caps.tools.get("whatweb"), "not installed (Linux/WSL only)"),
        ("testssl.sh", cfg.use_testssl, caps.tools.get("testssl"), "not installed (Linux/WSL only)"),
    )
    for name, wanted, available, why in checks:
        if wanted and not available:
            skipped.append(f"{name}: {why}")
        elif not wanted and only is None and name in ("nuclei", "whatweb", "testssl.sh") and available:
            skipped.append(f"{name}: installed but disabled for quick scans (run a full scan)")
    if only is None and not cfg.use_speedtest:
        skipped.append("speed test: disabled in netscan.yaml (scan.use_speedtest)")
    return cfg, skipped


def run_scan(
    cfg: ScanDefaults | None = None,
    network: str | None = None,
    full: bool | None = None,
    only: str | None = None,
    progress: ProgressFn | None = None,
) -> ScanResult:
    """Execute a scan and return the aggregated result.

    ``only``, when set, restricts the run to a single tool/stage — one of
    ``ONLY_STAGES`` — instead of the bundled quick/full pipeline. A host
    discovery still always runs first so the full current device set is
    known (online/offline bookkeeping and new-device alerts stay correct);
    only the optional enrichment stages are narrowed to the requested one.
    """
    cfg = cfg or ScanDefaults()
    if only is not None and only not in ONLY_STAGES:
        raise ValueError(f"unknown scan stage: {only!r}")
    caps = tools.Capabilities.detect()
    start = time.perf_counter()

    timings: list[StageTiming] = []

    def emit_progress(stage: str, done: int, total: int) -> None:
        if progress:
            progress(stage, done, total)

    network_cidr = network or cfg.network
    if network_cidr:
        ipaddress.IPv4Network(network_cidr, strict=False)  # validate
        local_ip, iface = "", "custom"
        try:
            primary = discovery._primary_ip()
            if ipaddress.IPv4Address(primary) in ipaddress.IPv4Network(network_cidr, strict=False):
                local_ip = primary
        except (OSError, ValueError):
            pass
    else:
        network_cidr, local_ip, iface = discovery.get_local_network()

    use_full = cfg.full if full is None else full
    if only in ("nmap", "rustscan"):
        use_full = True  # an explicit single-tool run should be thorough
    mode = f"only:{only}" if only else ("full" if use_full else "quick")
    cfg, skipped = _plan(cfg, caps, only, use_full)

    gateway_ip = discovery.default_gateway() or ""
    try:
        if gateway_ip and ipaddress.IPv4Address(gateway_ip) not in ipaddress.IPv4Network(
            network_cidr, strict=False
        ):
            gateway_ip = ""
    except ValueError:
        gateway_ip = ""

    emit(
        "scan",
        f"scan started · mode {mode} · network {network_cidr} · iface {iface}"
        + (f" · this host {local_ip}" if local_ip else "")
        + (f" · gateway {gateway_ip}" if gateway_ip else ""),
        mode=mode,
        network=network_cidr,
    )
    for reason in skipped:
        emit("scan", f"skipped — {reason}", "debug" if "disabled for quick" in reason else "info")

    emit_progress("arp", 0, 1)
    _t0 = time.perf_counter()
    scan_iface = iface if iface not in ("", "default", "custom") else None
    raw_devices, method = discovery.discover_hosts(
        network_cidr, iface=scan_iface, progress=lambda d, t: emit_progress("sweep", d, t)
    )
    timings.append(
        StageTiming(
            stage="arp" if method == "arp" else "sweep", duration_s=round(time.perf_counter() - _t0, 2)
        )
    )
    if local_ip:
        own_mac = discovery.local_mac(local_ip)
        own = next((d for d in raw_devices if d["ip"] == local_ip), None)
        if own is None and own_mac:
            raw_devices.append({"ip": local_ip, "mac": own_mac})
            raw_devices.sort(key=lambda d: ipaddress.IPv4Address(d["ip"]))
        elif own is not None and not own.get("mac"):
            own["mac"] = own_mac
    emit_progress("arp", 1, 1)
    emit(
        "discovery",
        f"{len(raw_devices)} hosts found by {'ARP' if method == 'arp' else 'ICMP sweep + ARP cache'} "
        f"in {fmt_s(time.perf_counter() - _t0)}",
        hosts=len(raw_devices),
        method=method,
    )

    needs_ports = only is None or only in ("nmap", "rustscan") or only in _WEB_STAGES
    if not needs_ports:
        ports_to_scan: dict[int, str] = {}
    elif only in _WEB_STAGES:
        # These only need to know which ports are web UIs, not their versions.
        ports_to_scan = dict(enrich.COMMON_PORTS)
    else:
        ports_to_scan = {**enrich.COMMON_PORTS, **enrich.EXTENDED_PORTS} if use_full else enrich.COMMON_PORTS

    # Main-thread, non-thread-safe steps first
    vendor_cache = enrich.resolve_vendors([d["mac"] for d in raw_devices if d.get("mac")])
    for raw in raw_devices:
        mac = raw.get("mac", "")
        emit(
            "discovery",
            f"{raw['ip']} is-at {mac or '?'}"
            + (f" · {vendor_cache.get(mac)}" if vendor_cache.get(mac) else ""),
            "debug",
            host=raw["ip"],
            mac=mac,
        )
    gateway_mac = next((d.get("mac", "") for d in raw_devices if d["ip"] == gateway_ip), "")

    mdns_map: dict[str, dict[str, object]] = {}
    if cfg.use_mdns and caps.mdns:
        emit_progress("mdns", 0, 1)
        _t0 = time.perf_counter()
        mdns_map = mdns.mdns_discover()
        timings.append(StageTiming(stage="mdns", duration_s=round(time.perf_counter() - _t0, 2)))
        emit_progress("mdns", 1, 1)

    devices: list[Device] = []
    total = len(raw_devices)
    emit_progress("enrich", 0, total)
    if ports_to_scan:
        emit(
            "scan",
            f"enriching {total} hosts · {cfg.workers} in parallel · {len(ports_to_scan)} TCP ports each "
            f"({'common + extended' if len(ports_to_scan) > len(enrich.COMMON_PORTS) else 'common'}) · "
            f"port timeout {int(cfg.port_timeout * 1000)} ms",
        )
    _t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=min(cfg.workers, max(total, 1))) as executor:
        futures = {
            executor.submit(_enrich_device, raw, ports_to_scan, vendor_cache, mdns_map, cfg, caps): raw
            for raw in raw_devices
        }
        for i, future in enumerate(as_completed(futures), 1):
            try:
                devices.append(future.result())
            except Exception as exc:
                # A single host must not sink the whole scan.
                logger.exception("Error enriching %s", futures[future].get("ip", "?"))
                emit("scan", f"✗ {futures[future].get('ip', '?')} enrichment failed: {exc}", "error")
            emit_progress("enrich", i, total)
    timings.append(StageTiming(stage="enrich", duration_s=round(time.perf_counter() - _t0, 2)))

    devices.sort(key=lambda d: ipaddress.IPv4Address(d.ip))

    # Vulnerability pass over discovered web UIs (opt-in, needs nuclei).
    # Capped: nuclei is slow and noisy, so never feed it an unbounded list.
    vulnerabilities: list[dict[str, str]] = []
    if cfg.use_nuclei and caps.tools.get("nuclei"):
        urls = [http.url for dev in devices for http in dev.http][: cfg.nuclei_max_targets]
        emit("scan", f"nuclei: auditing {len(urls)} web UIs (cap {cfg.nuclei_max_targets})")
        emit_progress("nuclei", 0, max(len(urls), 1))
        _t0 = time.perf_counter()
        # One target per run so the progress bar moves per web UI (a single
        # batched run would sit at 0 % for many minutes).
        for i, url in enumerate(urls, 1):
            vulnerabilities.extend(tools.nuclei_scan([url]))
            emit_progress("nuclei", i, len(urls))
        timings.append(StageTiming(stage="nuclei", duration_s=round(time.perf_counter() - _t0, 2)))

    # Web technology fingerprint of discovered web UIs (opt-in, needs whatweb).
    if cfg.use_whatweb and caps.tools.get("whatweb"):
        http_entries = [http for dev in devices for http in dev.http][: cfg.whatweb_max_targets]
        emit_progress("whatweb", 0, max(len(http_entries), 1))
        _t0 = time.perf_counter()
        for i, http in enumerate(http_entries, 1):
            http.tech = tools.whatweb_scan(http.url)
            emit_progress("whatweb", i, len(http_entries))
        timings.append(StageTiming(stage="whatweb", duration_s=round(time.perf_counter() - _t0, 2)))

    # TLS configuration audit of discovered HTTPS UIs (opt-in, needs testssl.sh).
    # Only reachable on Linux/WSL — no native Windows build of testssl.sh exists.
    if cfg.use_testssl and caps.tools.get("testssl"):
        https_targets = [
            (dev.ip, urlsplit(http.url).port or 443)
            for dev in devices
            for http in dev.http
            if http.tls is not None
        ][: cfg.testssl_max_targets]
        emit_progress("testssl", 0, max(len(https_targets), 1))
        _t0 = time.perf_counter()
        for i, (ip, port) in enumerate(https_targets, 1):
            vulnerabilities.extend(tools.testssl_scan(f"{ip}:{port}"))
            emit_progress("testssl", i, len(https_targets))
        timings.append(StageTiming(stage="testssl", duration_s=round(time.perf_counter() - _t0, 2)))

    ports_open_total = sum(len(d.open_ports) for d in devices)
    duration = round(time.perf_counter() - start, 2)
    emit(
        "scan",
        f"scan finished in {fmt_s(duration)} · {len(devices)} hosts · {ports_open_total} open ports · "
        f"{sum(len(d.http) for d in devices)} web UIs · {len(vulnerabilities)} findings · "
        + " · ".join(f"{t.stage} {fmt_s(t.duration_s)}" for t in timings),
        duration_s=duration,
    )

    return ScanResult(
        network=network_cidr,
        interface=iface,
        local_ip=local_ip,
        total_devices=len(devices),
        duration_s=duration,
        devices=devices,
        vulnerabilities=vulnerabilities,
        capabilities=caps.as_dict(),
        stage_timings=timings,
        ports_open_total=ports_open_total,
        link_speed_mbps=speed.local_link_speed_mbps(),
        speedtest_ran=cfg.use_speedtest,
        discovery_method=method,
        mode=mode,
        gateway_ip=gateway_ip,
        gateway_mac=gateway_mac,
        skipped=skipped,
        ports_scanned=sorted(ports_to_scan),
    )
