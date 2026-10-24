"""ICMP echo and layer-2 reachability probes, without spawning processes.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

The original implementation forked ``ping`` once per echo. That costs
30-80 ms of process start-up on Windows (more than a LAN round trip), makes
the live monitor fork ~16 processes per second, and on Windows it reports
``Reply from <router>: Destination host unreachable`` with exit code 0 — a
dead host counted as alive.

Backends, picked once per process (see :func:`backend`):

``win-api``   Windows ``IcmpSendEcho`` (iphlpapi.dll). No privileges needed.
              RTT is the wall-clock of the synchronous call (µs timer),
              clamped to ±1 ms of the kernel's own integer-ms RTT, so a
              scheduling hiccup can never inflate it by more than 1 ms.
``dgram``     Linux/macOS unprivileged ``SOCK_DGRAM``/``IPPROTO_ICMP`` socket
              (Linux needs ``net.ipv4.ping_group_range`` to include the
              user's group — the default on most current distributions).
``raw``       ``SOCK_RAW`` when running as root / with ``CAP_NET_RAW``.
``subprocess`` The system ``ping`` binary, as a last resort. Output must
              contain ``ttl=`` to count as a reply (rejects "unreachable").

All RTTs are **milliseconds** as ``float``.
"""

from __future__ import annotations

import ctypes
import os
import platform
import random
import re
import socket
import struct
import subprocess
import threading
import time

IS_WINDOWS = platform.system() == "Windows"

_backend: str | None = None
_backend_lock = threading.Lock()
_PAYLOAD_TAG = b"netscan-icmp"

# "time=0.412 ms", "time<1ms", "tiempo=12ms" (es), "Zeit=12ms" (de), ...
_PING_TIME_RE = re.compile(
    r"(?:time|tiempo|zeit|temps|tempo)\s*([=<])\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE
)
_TTL_RE = re.compile(r"\bttl[=:]\s*\d+", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Windows: iphlpapi
# --------------------------------------------------------------------------- #
class _IpOptionInformation(ctypes.Structure):
    _fields_ = [
        ("Ttl", ctypes.c_ubyte),
        ("Tos", ctypes.c_ubyte),
        ("Flags", ctypes.c_ubyte),
        ("OptionsSize", ctypes.c_ubyte),
        ("OptionsData", ctypes.c_void_p),
    ]


class _IcmpEchoReply(ctypes.Structure):
    _fields_ = [
        ("Address", ctypes.c_ulong),
        ("Status", ctypes.c_ulong),
        ("RoundTripTime", ctypes.c_ulong),
        ("DataSize", ctypes.c_ushort),
        ("Reserved", ctypes.c_ushort),
        ("Data", ctypes.c_void_p),
        ("Options", _IpOptionInformation),
    ]


_iphlpapi = None


def _win_lib():
    global _iphlpapi
    if _iphlpapi is None:
        lib = ctypes.WinDLL("iphlpapi")
        lib.IcmpCreateFile.restype = ctypes.c_void_p
        lib.IcmpCloseHandle.argtypes = [ctypes.c_void_p]
        lib.IcmpSendEcho.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ushort,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
        ]
        lib.IcmpSendEcho.restype = ctypes.c_ulong
        lib.SendARP.argtypes = [
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ulong),
        ]
        lib.SendARP.restype = ctypes.c_ulong
        _iphlpapi = lib
    return _iphlpapi


def _in_addr(ip: str) -> int:
    """IPv4 address as the network-byte-order DWORD iphlpapi expects."""
    return ctypes.c_ulong.from_buffer_copy(socket.inet_aton(ip)).value


def _win_echo(ip: str, timeout: float) -> float | None:
    lib = _win_lib()
    handle = lib.IcmpCreateFile()
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise OSError("IcmpCreateFile failed")
    payload = _PAYLOAD_TAG + os.urandom(4)
    size = ctypes.sizeof(_IcmpEchoReply) + len(payload) + 8
    buf = ctypes.create_string_buffer(size)
    try:
        start = time.perf_counter()
        replies = lib.IcmpSendEcho(
            handle, _in_addr(ip), payload, len(payload), None, buf, size, max(1, int(timeout * 1000))
        )
        elapsed = (time.perf_counter() - start) * 1000
    finally:
        lib.IcmpCloseHandle(handle)
    if not replies:
        return None
    reply = _IcmpEchoReply.from_buffer(buf)
    if reply.Status != 0:  # IP_SUCCESS; 11003 = dest host unreachable, 11010 = timed out
        return None
    kernel_ms = float(reply.RoundTripTime)
    return round(min(max(elapsed, kernel_ms - 1), kernel_ms + 1), 3)


def arp_probe(ip: str) -> str | None:
    """Layer-2 presence check: ARP who-has for ``ip`` → MAC, or None.

    Only implemented on Windows (``SendARP`` needs no privileges and really
    puts an ARP request on the wire). Answers even for hosts whose firewall
    drops ICMP and every TCP port — typical of a Windows PC. A miss costs
    ~4 s (three ARP retries), so callers only use it as the last resort.
    """
    if not IS_WINDOWS:
        return None
    try:
        lib = _win_lib()
        mac = (ctypes.c_ubyte * 6)()
        length = ctypes.c_ulong(6)
        rc = lib.SendARP(_in_addr(ip), 0, mac, ctypes.byref(length))
    except (OSError, AttributeError, ValueError):
        return None
    if rc != 0 or length.value != 6:
        return None
    value = ":".join(f"{b:02x}" for b in mac)
    return None if value == "00:00:00:00:00:00" else value


# --------------------------------------------------------------------------- #
# POSIX: datagram / raw ICMP sockets
# --------------------------------------------------------------------------- #
def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return ~total & 0xFFFF


def _sock_echo(ip: str, timeout: float, raw: bool) -> float | None:
    kind = socket.SOCK_RAW if raw else socket.SOCK_DGRAM
    with socket.socket(socket.AF_INET, kind, socket.IPPROTO_ICMP) as sock:
        ident = os.getpid() & 0xFFFF
        seq = random.randint(0, 0xFFFF)
        payload = _PAYLOAD_TAG + os.urandom(4)
        header = struct.pack("!BBHHH", 8, 0, 0, ident, seq)
        packet = struct.pack("!BBHHH", 8, 0, _checksum(header + payload), ident, seq) + payload
        deadline = time.perf_counter() + timeout
        start = time.perf_counter()
        sock.sendto(packet, (ip, 0))
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return None
            sock.settimeout(remaining)
            try:
                data, addr = sock.recvfrom(2048)
            except TimeoutError:
                return None
            elapsed = (time.perf_counter() - start) * 1000
            # Raw sockets (and macOS datagram ones) hand back the IP header too.
            if data and data[0] >> 4 == 4:
                data = data[(data[0] & 0x0F) * 4 :]
            if len(data) < 8 or addr[0] != ip:
                continue
            icmp_type, _code, _csum, _rid, rseq = struct.unpack("!BBHHH", data[:8])
            # Linux rewrites the identifier of datagram sockets, so match on
            # sequence + our random payload instead.
            if icmp_type == 0 and rseq == seq and data[8:] == payload:
                return round(elapsed, 3)


# --------------------------------------------------------------------------- #
# Subprocess fallback
# --------------------------------------------------------------------------- #
def _subprocess_echo(ip: str, timeout: float) -> float | None:
    count_flag = "-n" if IS_WINDOWS else "-c"
    wait_flag = "-w" if IS_WINDOWS else "-W"
    # Windows -w is in ms; Linux/BSD -W is whole seconds and 0 means "forever".
    wait_val = str(max(1, int(timeout * 1000))) if IS_WINDOWS else str(max(1, round(timeout)))
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
    if proc.returncode != 0 or not _TTL_RE.search(proc.stdout):
        return None
    match = _PING_TIME_RE.search(proc.stdout)
    if match:
        value = float(match.group(2).replace(",", "."))
        # "time<1ms" is an upper bound, not a measurement: report half of it.
        return round(value / 2 if match.group(1) == "<" else value, 3)
    return round(elapsed, 3)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def _select_backend() -> str:
    if IS_WINDOWS:
        try:
            _win_lib()
            return "win-api"
        except (OSError, AttributeError):
            return "subprocess"
    for raw, name in ((False, "dgram"), (True, "raw")):
        try:
            kind = socket.SOCK_RAW if raw else socket.SOCK_DGRAM
            socket.socket(socket.AF_INET, kind, socket.IPPROTO_ICMP).close()
            return name
        except OSError:
            continue
    return "subprocess"


def backend() -> str:
    """Name of the ICMP implementation in use (shown in /api/capabilities)."""
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                _backend = _select_backend()
    return _backend


def echo(ip: str, timeout: float = 1.0) -> float | None:
    """Send one ICMP echo to ``ip``; RTT in ms, or None on loss/unreachable."""
    global _backend
    impl = backend()
    try:
        if impl == "win-api":
            return _win_echo(ip, timeout)
        if impl in ("dgram", "raw"):
            return _sock_echo(ip, timeout, raw=impl == "raw")
    except PermissionError:
        _backend = "subprocess"  # sandbox/seccomp changed its mind: degrade for good
    except OSError:
        return None  # host/network unreachable surfaces as OSError on POSIX sockets
    return _subprocess_echo(ip, timeout)
