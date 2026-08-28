"""Host / server / frontend runtime status.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Powers the dashboard's "system status" panel: everything about the machine
the backend runs on (CPU, memory, disk, network, load, uptime), the backend
process itself, the Python runtime, and the state of the built frontend
bundle. ``psutil`` is an optional import — if it is missing the host section
degrades to whatever the standard library can provide.
"""

from __future__ import annotations

import os
import platform
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

psutil: Any
try:
    import psutil as _psutil

    psutil = _psutil
except ImportError:  # optional dependency
    psutil = None

# Process start time — set once at import so uptime is stable.
_PROCESS_START = time.time()

# Cached net counters for rate calculation between polls.
_LAST_NET: dict[str, float] = {}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def cpu_info() -> dict[str, object]:
    if psutil is None:
        return {"available": False, "logical": os.cpu_count() or 0}
    freq = _safe(psutil.cpu_freq)
    load = _safe(lambda: list(psutil.getloadavg()))
    return {
        "available": True,
        "percent": _safe(lambda: psutil.cpu_percent(interval=None), 0.0),
        "per_core": _safe(lambda: psutil.cpu_percent(interval=None, percpu=True), []),
        "logical": _safe(lambda: psutil.cpu_count(logical=True), os.cpu_count()),
        "physical": _safe(lambda: psutil.cpu_count(logical=False)),
        "freq_mhz": round(freq.current, 0) if freq else None,
        "freq_max_mhz": round(freq.max, 0) if freq and freq.max else None,
        "load_avg": load,
    }


def memory_info() -> dict[str, object]:
    if psutil is None:
        return {"available": False}
    vm = _safe(psutil.virtual_memory)
    sw = _safe(psutil.swap_memory)
    out: dict[str, object] = {"available": True}
    if vm:
        out.update(
            total=vm.total,
            used=vm.used,
            free=vm.available,
            percent=vm.percent,
        )
    if sw:
        out.update(swap_total=sw.total, swap_used=sw.used, swap_percent=sw.percent)
    return out


def disk_info() -> list[dict[str, object]]:
    if psutil is None:
        return []
    disks: list[dict[str, object]] = []
    for part in _safe(psutil.disk_partitions, []) or []:
        if "cdrom" in part.opts or part.fstype == "":
            continue
        usage = _safe(lambda p=part.mountpoint: psutil.disk_usage(p))
        if not usage:
            continue
        disks.append(
            {
                "mount": part.mountpoint,
                "device": part.device,
                "fstype": part.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
            }
        )
    return disks


def network_info() -> dict[str, object]:
    if psutil is None:
        return {"available": False, "interfaces": []}
    stats = _safe(psutil.net_if_stats, {}) or {}
    addrs = _safe(psutil.net_if_addrs, {}) or {}
    io = _safe(lambda: psutil.net_io_counters(pernic=True), {}) or {}
    now = time.time()
    interfaces: list[dict[str, object]] = []
    for name, st in stats.items():
        if name.lower().startswith(("lo", "loopback")):
            continue
        ipv4 = ""
        mac = ""
        for a in addrs.get(name, []):
            if a.family == socket.AF_INET:
                ipv4 = a.address
            elif getattr(a, "family", None) == getattr(psutil, "AF_LINK", -1):
                mac = a.address
        counters = io.get(name)
        sent = counters.bytes_sent if counters else 0
        recv = counters.bytes_recv if counters else 0
        # Byte-rate since last poll of this interface.
        prev_ts = _LAST_NET.get(f"{name}_ts")
        up_bps = down_bps = 0.0
        if prev_ts:
            dt = now - prev_ts
            if dt > 0:
                up_bps = max(0.0, (sent - _LAST_NET.get(f"{name}_sent", sent)) / dt)
                down_bps = max(0.0, (recv - _LAST_NET.get(f"{name}_recv", recv)) / dt)
        _LAST_NET[f"{name}_ts"] = now
        _LAST_NET[f"{name}_sent"] = sent
        _LAST_NET[f"{name}_recv"] = recv
        interfaces.append(
            {
                "name": name,
                "is_up": st.isup,
                "speed_mbps": st.speed if st.speed > 0 else None,
                "mtu": st.mtu,
                "ipv4": ipv4,
                "mac": mac,
                "bytes_sent": sent,
                "bytes_recv": recv,
                "up_bps": round(up_bps, 0),
                "down_bps": round(down_bps, 0),
            }
        )
    interfaces.sort(key=lambda i: (not i["is_up"], -int(i["bytes_recv"] or 0)))  # type: ignore[call-overload]
    return {"available": True, "interfaces": interfaces}


def process_info() -> dict[str, object]:
    out: dict[str, object] = {
        "pid": os.getpid(),
        "uptime_seconds": round(time.time() - _PROCESS_START, 1),
        "python": platform.python_version(),
        "executable": sys.executable,
    }
    if psutil is None:
        return out
    proc = _safe(lambda: psutil.Process(os.getpid()))
    if proc is None:
        return out
    with _safe(lambda: proc.oneshot()) or _nullctx():
        mem = _safe(proc.memory_info)
        out.update(
            cpu_percent=_safe(lambda: proc.cpu_percent(interval=None), 0.0),
            rss=mem.rss if mem else None,
            threads=_safe(proc.num_threads),
            open_files=_safe(lambda: len(proc.open_files() or [])),
            connections=_safe(lambda: len(proc.net_connections() or [])),
            create_time=_safe(lambda: datetime.fromtimestamp(proc.create_time()).isoformat()),
        )
    return out


class _nullctx:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


def host_info() -> dict[str, object]:
    boot = None
    uptime = None
    if psutil is not None:
        boot_ts = _safe(psutil.boot_time)
        if boot_ts:
            boot = datetime.fromtimestamp(boot_ts).isoformat()
            uptime = round(time.time() - boot_ts, 0)
    return {
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "arch": platform.machine(),
        "boot_time": boot,
        "uptime_seconds": uptime,
        "cpu_model": platform.processor() or platform.machine(),
    }


def frontend_status(dist_dir: Path | None = None) -> dict[str, object]:
    """Whether the built dashboard bundle exists and its size / build time.

    If ``dist_dir`` is given, only that directory is checked; otherwise the
    repo-adjacent ``frontend/dist`` locations are auto-detected.
    """
    if dist_dir is not None:
        candidates = [dist_dir]
    else:
        here = Path(__file__).resolve()
        # backend/src/netscan/system.py -> repo root is parents[3]
        candidates = [here.parents[3] / "frontend" / "dist", Path.cwd() / "frontend" / "dist"]
    for cand in candidates:
        if cand and (cand / "index.html").is_file():
            total = 0
            files = 0
            newest = 0.0
            for f in cand.rglob("*"):
                if f.is_file():
                    stat = f.stat()
                    total += stat.st_size
                    files += 1
                    newest = max(newest, stat.st_mtime)
            return {
                "built": True,
                "path": str(cand),
                "files": files,
                "size_bytes": total,
                "built_at": datetime.fromtimestamp(newest).isoformat() if newest else None,
            }
    return {"built": False, "path": None}


def collect(dist_dir: Path | None = None) -> dict[str, object]:
    """Full system snapshot for the /api/system endpoint."""
    return {
        "timestamp": datetime.now().isoformat(),
        "host": host_info(),
        "cpu": cpu_info(),
        "memory": memory_info(),
        "disks": disk_info(),
        "network": network_info(),
        "process": process_info(),
        "frontend": frontend_status(dist_dir),
        "psutil": psutil is not None,
    }
