"""Per-device speed and quality metrics.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

This module measures link and service quality for each discovered device
without depending on external tools:

* **Latency statistics** — several ICMP echoes per host, reduced to
  avg / min / max / jitter (mean deviation) and packet loss %.
* **TCP handshake time** — how many milliseconds the 3-way handshake takes
  on every open port; a cheap proxy for how snappy a service feels.
* **Throughput** — optional HTTP download from a web port to estimate the
  real transfer rate (Mbit/s) toward the device.
* **Link speed** — the negotiated speed of the *local* network adapter
  (1G / 2.5G / 10G ...), reported once for the host.

Everything degrades gracefully: a metric that cannot be measured comes back
as ``None`` instead of raising.
"""

from __future__ import annotations

import platform
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import pairwise
from statistics import fmean, pstdev

from netscan.models import DeviceMetrics, PortInfo

# One HTTP GET of at most this many bytes is enough to estimate throughput
# on a homelab LAN without hammering the target.
_THROUGHPUT_MAX_BYTES = 4 * 1024 * 1024  # 4 MiB
_PING_TIME_RE = re.compile(
    r"(?:time|tiempo|zeit|temps|tempo)\s*[=<]\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE
)


# --------------------------------------------------------------------------- #
# Latency / jitter / loss
# --------------------------------------------------------------------------- #
def _ping_once(ip: str, timeout: float) -> float | None:
    """Single ICMP echo. Returns RTT in ms or None on loss/error."""
    is_windows = platform.system().lower() == "windows"
    count_flag = "-n" if is_windows else "-c"
    wait_flag = "-w" if is_windows else "-W"
    wait_val = str(int(timeout * 1000)) if is_windows else str(max(int(timeout), 1))
    try:
        start = time.perf_counter()
        proc = subprocess.run(
            ["ping", count_flag, "1", wait_flag, wait_val, ip],
            capture_output=True,
            text=True,
            timeout=timeout + 2,
            check=False,
        )
        elapsed = (time.perf_counter() - start) * 1000
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    match = _PING_TIME_RE.search(proc.stdout)
    if match:
        return round(float(match.group(1).replace(",", ".")), 2)
    return round(elapsed, 2)


def latency_stats(ip: str, count: int = 5, timeout: float = 1.0) -> dict[str, float | None]:
    """Send ``count`` pings; reduce them to avg/min/max/jitter/loss."""
    samples: list[float] = []
    lost = 0
    for _ in range(max(count, 1)):
        rtt = _ping_once(ip, timeout)
        if rtt is None:
            lost += 1
        else:
            samples.append(rtt)
    total = max(count, 1)
    loss_pct = round(lost / total * 100, 1)
    if not samples:
        return {
            "latency_avg_ms": None,
            "latency_min_ms": None,
            "latency_max_ms": None,
            "jitter_ms": None,
            "packet_loss_pct": loss_pct,
        }
    # Jitter as the mean absolute successive difference (RFC 3550 style),
    # falling back to population stdev for a single successful sample.
    if len(samples) > 1:
        diffs = [abs(b - a) for a, b in pairwise(samples)]
        jitter = round(fmean(diffs), 2) if diffs else round(pstdev(samples), 2)
    else:
        jitter = 0.0
    return {
        "latency_avg_ms": round(fmean(samples), 2),
        "latency_min_ms": round(min(samples), 2),
        "latency_max_ms": round(max(samples), 2),
        "jitter_ms": jitter,
        "packet_loss_pct": loss_pct,
    }


# --------------------------------------------------------------------------- #
# TCP handshake time per open port
# --------------------------------------------------------------------------- #
def tcp_connect_ms(ip: str, port: int, timeout: float = 2.0) -> float | None:
    """Time the TCP 3-way handshake to ``ip:port`` in milliseconds."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            start = time.perf_counter()
            if sock.connect_ex((ip, port)) != 0:
                return None
            return round((time.perf_counter() - start) * 1000, 2)
    except OSError:
        return None


def port_connect_times(
    ip: str, ports: list[int], workers: int = 8, timeout: float = 2.0
) -> dict[int, float]:
    """Measure handshake time for every port concurrently. {port: ms}."""
    results: dict[int, float] = {}
    if not ports:
        return results
    with ThreadPoolExecutor(max_workers=min(workers, len(ports))) as pool:
        futures = {pool.submit(tcp_connect_ms, ip, p, timeout): p for p in ports}
        for fut in as_completed(futures):
            value = fut.result()
            if value is not None:
                results[futures[fut]] = value
    return results


# --------------------------------------------------------------------------- #
# Throughput (optional, needs an HTTP port)
# --------------------------------------------------------------------------- #
def http_throughput_mbps(
    ip: str, port: int, max_bytes: int = _THROUGHPUT_MAX_BYTES, timeout: float = 8.0
) -> float | None:
    """Estimate download throughput (Mbit/s) by streaming from an HTTP port."""
    import httpx

    scheme = "https" if port in {443, 8443, 8006} else "http"
    url = f"{scheme}://{ip}:{port}/"
    downloaded = 0
    try:
        start = time.perf_counter()
        with (
            httpx.Client(verify=False, follow_redirects=True, timeout=timeout) as client,
            client.stream("GET", url) as resp,
        ):
            for chunk in resp.iter_bytes(chunk_size=65536):
                downloaded += len(chunk)
                if downloaded >= max_bytes:
                    break
        elapsed = time.perf_counter() - start
    except Exception:
        return None
    if downloaded < 16384 or elapsed <= 0:
        # Too little data to be meaningful (tiny login page, etc.).
        return None
    return round((downloaded * 8) / elapsed / 1_000_000, 2)


# --------------------------------------------------------------------------- #
# Local adapter link speed
# --------------------------------------------------------------------------- #
def local_link_speed_mbps() -> int | None:
    """Negotiated speed of the active local NIC in Mbit/s, or None."""
    try:
        import psutil
    except ImportError:
        return None
    try:
        stats = psutil.net_if_stats()
        io = psutil.net_io_counters(pernic=True)
    except Exception:
        return None
    best: int | None = None
    # Pick the up interface with the most traffic and a real reported speed.
    for name, st in stats.items():
        if not st.isup or st.speed <= 0:
            continue
        if name.lower().startswith(("lo", "loopback")):
            continue
        traffic = 0
        counters = io.get(name)
        if counters is not None:
            traffic = counters.bytes_sent + counters.bytes_recv
        if best is None or traffic > 0:
            best = st.speed if best is None else max(best, st.speed)
    return best


# --------------------------------------------------------------------------- #
# Quality score
# --------------------------------------------------------------------------- #
def quality_score(metrics: DeviceMetrics) -> int:
    """0-100 heuristic combining loss, latency and jitter (higher = better)."""
    score = 100.0
    if metrics.packet_loss_pct is not None:
        score -= metrics.packet_loss_pct * 0.8  # loss dominates
    if metrics.latency_avg_ms is not None:
        # Penalise latency above 1 ms, capped.
        score -= min(max(metrics.latency_avg_ms - 1, 0) * 1.2, 40)
    if metrics.jitter_ms is not None:
        score -= min(metrics.jitter_ms * 2, 20)
    return max(0, min(100, round(score)))


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def measure_device(
    ip: str,
    open_ports: list[PortInfo] | None = None,
    *,
    count: int = 5,
    ping_timeout: float = 1.0,
    throughput: bool = False,
    throughput_ports: set[int] | None = None,
) -> DeviceMetrics:
    """Full metrics sweep for one device."""
    open_ports = open_ports or []
    stats = latency_stats(ip, count=count, timeout=ping_timeout)
    metrics = DeviceMetrics(**stats)  # type: ignore[arg-type]

    port_numbers = [p.port for p in open_ports]
    metrics.tcp_connect_ms = port_connect_times(ip, port_numbers)
    if metrics.tcp_connect_ms:
        metrics.tcp_connect_avg_ms = round(fmean(metrics.tcp_connect_ms.values()), 2)

    if throughput:
        candidates = throughput_ports or {80, 8080, 8096, 8000, 5000, 9000, 3000}
        for p in port_numbers:
            if p in candidates:
                mbps = http_throughput_mbps(ip, p)
                if mbps is not None:
                    metrics.throughput_mbps = mbps
                    metrics.throughput_port = p
                    break

    metrics.quality = quality_score(metrics)
    return metrics
