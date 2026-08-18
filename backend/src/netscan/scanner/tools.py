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

import shutil
import subprocess
from dataclasses import dataclass, field

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
    """Run an external tool and return stdout, or None on any failure."""
    if not shutil.which(binary):
        return None
    try:
        proc = subprocess.run(
            [binary, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
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
    return versions


def nmap_os_scan(ip: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Run ``nmap -O`` (requires privileges); return the OS guess or ''."""
    out = run_tool("nmap", ["-O", "--osscan-guess", "-Pn", ip], timeout)
    if not out:
        return ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith(("OS details:", "Aggressive OS guesses:")):
            return line.split(":", 1)[1].strip()
    return ""
