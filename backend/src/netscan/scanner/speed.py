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

import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import pairwise
from statistics import fmean, pstdev
from typing import Any

from netscan.events import emit, fmt_ms
from netscan.models import DeviceMetrics, PortInfo
from netscan.scanner import icmp

# One HTTP GET of at most this many bytes is enough to estimate throughput
# on a homelab LAN without hammering the target.
_THROUGHPUT_MAX_BYTES = 4 * 1024 * 1024  # 4 MiB


# --------------------------------------------------------------------------- #
# Latency / jitter / loss
# --------------------------------------------------------------------------- #
def _ping_once(ip: str, timeout: float) -> float | None:
    """Single ICMP echo. Returns RTT in ms or None on loss/error."""
    return icmp.echo(ip, timeout)


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
        emit("speed", f"{ip}: 0/{total} echoes answered · loss 100.0 % (ICMP filtered or host down)", host=ip)
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
        jitter = round(fmean(diffs), 3) if diffs else round(pstdev(samples), 3)
    else:
        jitter = 0.0
    stats: dict[str, float | None] = {
        "latency_avg_ms": round(fmean(samples), 3),
        "latency_min_ms": round(min(samples), 3),
        "latency_max_ms": round(max(samples), 3),
        "jitter_ms": jitter,
        "packet_loss_pct": loss_pct,
    }
    payload: dict[str, Any] = dict(stats)
    emit(
        "speed",
        f"{ip}: {len(samples)}/{total} echoes · avg {fmt_ms(stats['latency_avg_ms'])} · "
        f"min {fmt_ms(stats['latency_min_ms'])} · max {fmt_ms(stats['latency_max_ms'])} · "
        f"jitter {fmt_ms(jitter)} · loss {loss_pct:.1f} %",
        host=ip,
        **payload,
    )
    return stats


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


def port_connect_times(ip: str, ports: list[int], workers: int = 8, timeout: float = 2.0) -> dict[int, float]:
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
    """Estimate download throughput (Mbit/s, 1 Mbit = 10^6 bit) from an HTTP port.

    The clock starts at the first body byte, not at connect(): TCP/TLS
    set-up and the server's think time are latency, not bandwidth, and on a
    small page they used to dominate and report a fraction of the real rate.
    """
    import httpx

    scheme = "https" if port in {443, 8443, 8006, 9443, 5001} else "http"
    url = f"{scheme}://{ip}:{port}/"
    downloaded = 0
    first_byte_at: float | None = None
    try:
        start = time.perf_counter()
        with (
            httpx.Client(verify=False, follow_redirects=True, timeout=timeout) as client,
            client.stream("GET", url) as resp,
        ):
            for chunk in resp.iter_bytes(chunk_size=65536):
                if first_byte_at is None:
                    first_byte_at = time.perf_counter()
                downloaded += len(chunk)
                if downloaded >= max_bytes:
                    break
        end = time.perf_counter()
    except Exception as exc:
        emit("speed", f"throughput {url} failed: {exc}", "debug", host=ip)
        return None
    if first_byte_at is None:
        return None
    transfer = end - first_byte_at
    if downloaded < 262144 or transfer <= 0:
        # < 256 KiB: one TCP window or two — measures latency, not bandwidth.
        emit(
            "speed",
            f"throughput {url}: only {downloaded / 1024:.0f} KiB served — too small to measure bandwidth",
            "debug",
            host=ip,
        )
        return None
    mbps = round((downloaded * 8) / transfer / 1_000_000, 2)
    emit(
        "speed",
        f"throughput {url}: {downloaded / 1048576:.2f} MiB in {transfer * 1000:.0f} ms → {mbps} Mbit/s "
        f"(TTFB {(first_byte_at - start) * 1000:.0f} ms excluded)",
        host=ip,
        mbps=mbps,
    )
    return mbps


# --------------------------------------------------------------------------- #
# Local adapter link speed
# --------------------------------------------------------------------------- #
def local_link_speed_mbps() -> int | None:
    """Negotiated speed (Mbit/s) of the adapter that owns the primary IPv4.

    The previous heuristic took the fastest "up" adapter with any traffic,
    which on Windows is usually a Hyper-V/WSL vEthernet reporting a
    fictitious 10 Gbit/s.
    """
    try:
        import psutil
    except ImportError:
        return None
    try:
        from netscan.scanner.discovery import _primary_ip

        primary = _primary_ip()
        stats = psutil.net_if_stats()
        for name, addrs in psutil.net_if_addrs().items():
            if any(a.family == socket.AF_INET and a.address == primary for a in addrs):
                st = stats.get(name)
                return st.speed if st and st.isup and st.speed > 0 else None
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------- #
# Quality score
# --------------------------------------------------------------------------- #
def quality_score(metrics: DeviceMetrics) -> int:
    """0-100 heuristic combining loss, latency and jitter (higher = better).

    score = 100 - loss% - min(1.2 * (latency - 1 ms), 40) - min(2 * jitter, 20).
    Loss is subtracted 1:1, so a host that answered no echo (100 % loss)
    scores 0 — previously it was weighted 0.8 and a dead host scored 20.
    """
    if metrics.packet_loss_pct is not None and metrics.packet_loss_pct >= 100:
        return 0
    score = 100.0
    if metrics.packet_loss_pct is not None:
        score -= metrics.packet_loss_pct
    if metrics.latency_avg_ms is not None:
        # Penalise latency above 1 ms, capped.
        score -= min(max(metrics.latency_avg_ms - 1, 0) * 1.2, 40)
    if metrics.jitter_ms is not None:
        score -= min(metrics.jitter_ms * 2, 20)
    return max(0, min(100, round(score)))


def _tcp_rtt_fallback(
    ip: str, metrics: DeviceMetrics, port_numbers: list[int], count: int, timeout: float
) -> bool:
    """RTT from repeated TCP handshakes when ICMP is filtered.

    A Windows PC drops echo requests by default but completes the 3-way
    handshake on its open ports; the SYN → SYN/ACK time is one round trip,
    so it is a valid RTT sample. Loss here = handshakes that failed.
    """
    candidates = sorted(metrics.tcp_connect_ms) or port_numbers
    if not candidates:
        return False
    port = candidates[0]
    samples = [tcp_connect_ms(ip, port, timeout=timeout) for _ in range(max(count, 1))]
    ok = [s for s in samples if s is not None]
    if not ok:
        return False
    metrics.latency_avg_ms = round(fmean(ok), 3)
    metrics.latency_min_ms = round(min(ok), 3)
    metrics.latency_max_ms = round(max(ok), 3)
    metrics.jitter_ms = round(fmean(abs(b - a) for a, b in pairwise(ok)), 3) if len(ok) > 1 else 0.0
    metrics.packet_loss_pct = round(100 * (len(samples) - len(ok)) / len(samples), 1)
    metrics.rtt_source = f"tcp/{port}"
    emit(
        "speed",
        f"{ip}: ICMP filtered → RTT from {len(samples)} TCP handshakes to port {port}: "
        f"avg {fmt_ms(metrics.latency_avg_ms)} · jitter {fmt_ms(metrics.jitter_ms)} · "
        f"failed {metrics.packet_loss_pct:.1f} %",
        host=ip,
        port=port,
    )
    return True


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

    if metrics.latency_avg_ms is None and not _tcp_rtt_fallback(
        ip, metrics, port_numbers, count, ping_timeout
    ):
        # Nothing answered: an ICMP-filtering host with no open port (or a
        # host gone since discovery). That is "not measurable", not "quality
        # 0" — and 100 % ICMP loss is not link loss when ICMP is filtered.
        metrics.packet_loss_pct = None
        metrics.rtt_source = ""
        emit(
            "speed",
            f"{ip}: no ICMP echo and no TCP port answered — RTT and quality not measurable "
            "(ICMP filtered by the host firewall, or the host left)",
            host=ip,
        )
        return metrics

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
