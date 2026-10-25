"""External tool capability detection and subprocess wrappers.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later

Tools under GPL/AGPL/NPSL (nmap, rustscan, masscan, nuclei, whatweb,
testssl.sh) are invoked as separate processes — "mere aggregation" at arm's
length — so their licenses do not affect NetScan's GPL-2.0-or-later.
Every wrapper degrades gracefully: if the binary is missing, the feature
is reported as unavailable and skipped.
"""

from __future__ import annotations

import contextlib
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field

from netscan.events import emit, fmt_s

DEFAULT_TIMEOUT = 120


@dataclass(frozen=True)
class ToolSpec:
    name: str
    binary: str
    license: str
    purpose: str

    @property
    def available(self) -> bool:
        return shutil.which(self.binary) is not None


TOOLS: dict[str, ToolSpec] = {
    "nmap": ToolSpec("nmap", "nmap", "NPSL", "Service/version detection, OS fingerprinting, NSE scripts"),
    "rustscan": ToolSpec("rustscan", "rustscan", "GPL-3.0-only", "Ultra-fast port scanning (feeds nmap)"),
    "masscan": ToolSpec("masscan", "masscan", "AGPL-3.0-only", "Large-scale port scanning"),
    "nuclei": ToolSpec("nuclei", "nuclei", "MIT", "Template-based vulnerability scanning"),
    "whatweb": ToolSpec("whatweb", "whatweb", "GPL-2.0-only", "Web technology fingerprinting"),
    "testssl": ToolSpec("testssl.sh", "testssl.sh", "GPL-2.0-only", "TLS configuration auditing"),
}


@dataclass
class Capabilities:
    """Snapshot of what this machine can do right now."""

    tools: dict[str, bool] = field(default_factory=dict)
    mdns: bool = False

    @classmethod
    def detect(cls) -> Capabilities:
        caps = cls(tools={key: spec.available for key, spec in TOOLS.items()})
        try:
            import zeroconf  # noqa: F401

            caps.mdns = True
        except ImportError:
            caps.mdns = False
        return caps

    def as_dict(self) -> dict[str, bool]:
        return {**self.tools, "mdns": self.mdns}


def run_tool(binary: str, args: list[str], timeout: int = DEFAULT_TIMEOUT) -> str | None:
    """Run an external tool and return stdout, or None on any failure.

    The exact command line, exit code, duration and output size go to the
    event feed, so the dashboard terminal shows what really ran.
    """
    if not shutil.which(binary):
        emit("tool", f"{binary}: not installed — stage skipped", "debug", tool=binary)
        return None
    cmdline = shlex.join([binary, *args])
    emit("tool", f"$ {cmdline}", tool=binary, cmd=cmdline, timeout_s=timeout)
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [binary, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        emit("tool", f"{binary}: killed after the {timeout} s timeout", "warning", tool=binary)
        return None
    except OSError as exc:
        emit("tool", f"{binary}: could not start ({exc})", "error", tool=binary)
        return None
    elapsed = time.perf_counter() - start
    level = "info" if proc.returncode == 0 else "warning"
    detail = ""
    if proc.returncode != 0 and proc.stderr:
        detail = f" · stderr: {proc.stderr.strip().splitlines()[-1][:200]}"
    emit(
        "tool",
        f"{binary}: exit {proc.returncode} in {fmt_s(elapsed)} · {len(proc.stdout.splitlines())} lines of output{detail}",
        level,
        tool=binary,
        exit_code=proc.returncode,
        seconds=round(elapsed, 2),
    )
    return proc.stdout if proc.returncode == 0 else None


def nmap_service_scan(ip: str, ports: list[int], timeout: int = DEFAULT_TIMEOUT) -> dict[int, str]:
    """Run ``nmap -sV`` on the given ports; return {port: version string}."""
    if not ports:
        return {}
    port_arg = ",".join(str(p) for p in ports)
    out = run_tool("nmap", ["-sV", "--version-intensity", "2", "-Pn", "-p", port_arg, ip], timeout)
    versions: dict[int, str] = {}
    if not out:
        return versions
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and "/" in parts[0] and parts[1] == "open":
            try:
                port = int(parts[0].split("/")[0])
            except ValueError:
                continue
            versions[port] = " ".join(parts[2:])
            emit("nmap", f"{ip}:{port}/tcp → {versions[port]}", host=ip, port=port, version=versions[port])
    return versions


def nmap_os_scan(ip: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Run ``nmap -O`` (requires privileges); return the OS guess or ''."""
    out = run_tool("nmap", ["-O", "--osscan-guess", "-Pn", ip], timeout)
    if not out:
        return ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(("OS details:", "Aggressive OS guesses:")):
            guess = line.split(":", 1)[1].strip()
            emit("nmap", f"{ip}: OS guess → {guess}", host=ip)
            return guess
    return ""


def rustscan_ports(ip: str, timeout: int = 60) -> list[int]:
    """Fast full-range port discovery with RustScan (``-g`` greppable output)."""
    out = run_tool("rustscan", ["-a", ip, "-g", "--ulimit", "5000"], timeout)
    if not out:
        return []
    for line in out.splitlines():
        if "->" in line:
            try:
                ports = [int(p) for p in line.split("->", 1)[1].strip().strip("[]").split(",")]
            except ValueError:
                continue
            emit(
                "ports",
                f"rustscan {ip}: 65535 ports swept → open {', '.join(map(str, ports))}",
                host=ip,
                open=ports,
            )
            return ports
    return []


def parse_nuclei_line(line: str) -> dict[str, str] | None:
    """Parse one JSON line of nuclei output."""
    import json as _json

    try:
        data = _json.loads(line)
    except ValueError:
        return None
    return {
        "tool": "nuclei",
        "template": str(data.get("template-id", data.get("templateID", ""))),
        "severity": str(data.get("info", {}).get("severity", "")),
        "name": str(data.get("info", {}).get("name", "")),
        "matched_at": str(data.get("matched-at", data.get("matched", ""))),
    }


def nuclei_scan(
    urls: list[str], timeout: int = 300, severity: str = "medium,high,critical"
) -> list[dict[str, str]]:
    """Run nuclei against discovered web UIs. Returns parsed findings."""
    if not urls:
        return []
    findings: list[dict[str, str]] = []
    for url in urls[:20]:  # bounded: homelab scale
        out = run_tool(
            "nuclei",
            ["-u", url, "-silent", "-jsonl", "-severity", severity, "-timeout", "10"],
            timeout,
        )
        if not out:
            continue
        for line in out.splitlines():
            parsed = parse_nuclei_line(line)
            if parsed:
                findings.append(parsed)
                emit(
                    "vuln",
                    f"nuclei [{parsed['severity']}] {parsed['name'] or parsed['template']} → {parsed['matched_at']}",
                    "error" if parsed["severity"] in ("high", "critical") else "warning",
                    **parsed,
                )
    return findings


def whatweb_scan(url: str, timeout: int = 30) -> list[str]:
    """Web technology fingerprint via whatweb (``--log-json``-free, line parse)."""
    out = run_tool("whatweb", ["--color=never", "-a", "1", url], timeout)
    if not out:
        return []
    for line in out.splitlines():
        if line.startswith("http"):
            # "http://x [200 OK] Apache[2.4.1], PHP[8.1], ..."
            _, _, rest = line.partition("]")
            tech = [t.strip() for t in rest.split(",") if t.strip()][:20]
            emit("http", f"whatweb {url} → {', '.join(tech) or 'nothing identified'}", url=url)
            return tech
    return []


# Findings at these severities are noise for a homelab TLS audit — every
# host reports dozens of "OK"/"INFO" lines even when perfectly configured.
_TESTSSL_IGNORE_SEVERITIES = {"OK", "INFO", "DEBUG", ""}


def testssl_scan(target: str, timeout: int = 180) -> list[dict[str, str]]:
    """Run testssl.sh against ``host`` or ``host:port``; return parsed findings.

    testssl.sh's normal stdout is a very verbose, human-formatted transcript
    not meant for parsing, so this asks it to also write structured JSON to
    a temp file (``--jsonfile``) and reads that instead. Not distributed —
    "mere aggregation", like every other tool in this module (see the module
    docstring); only reachable when the binary is on PATH (Linux/WSL — no
    native Windows build exists).
    """
    if not shutil.which("testssl.sh"):
        return []
    fd, out_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    emit("tool", f"$ testssl.sh --quiet --color 0 --jsonfile={out_path} {target}", tool="testssl.sh")
    try:
        subprocess.run(
            ["testssl.sh", "--quiet", "--color", "0", f"--jsonfile={out_path}", target],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        import json as _json

        try:
            with open(out_path, encoding="utf-8") as f:
                raw = _json.load(f)
        except (OSError, ValueError):
            return []
    except (subprocess.TimeoutExpired, OSError):
        return []
    finally:
        with contextlib.suppress(OSError):
            os.unlink(out_path)

    if not isinstance(raw, list):
        return []
    findings: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "")).upper()
        if severity in _TESTSSL_IGNORE_SEVERITIES:
            continue
        findings.append(
            {
                "tool": "testssl",
                "template": str(item.get("id", "")),
                "severity": severity.lower(),
                "name": str(item.get("finding", "")),
                "matched_at": target,
            }
        )
        emit(
            "vuln",
            f"testssl [{severity.lower()}] {item.get('id', '')}: {item.get('finding', '')} → {target}",
            "warning",
        )
    return findings
