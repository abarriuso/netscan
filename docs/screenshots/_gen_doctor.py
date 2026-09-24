"""Generates docs/screenshots/doctor-cli.svg (and .png) by reproducing the real
`netscan doctor` output with Rich (record=True -> save_svg). Realistic sample
data, so the screenshot is representative even without the tools installed.

Usage:  backend/.venv-linux/bin/python docs/screenshots/_gen_doctor.py
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

console = Console(record=True, width=84)


def build() -> Table:
    table = Table(title="NetScan — diagnosis", header_style="bold cyan")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail", style="dim")

    OK = "[green]OK[/green]"
    WARN = "[yellow]warning[/yellow]"

    rows = [
        ("Python", OK, "3.12.3"),
        ("Privileges (ARP)", OK, "elevated"),
        ("tool: nmap", OK, "Service/version detection, OS fingerprinting"),
        ("tool: rustscan", OK, "Ultra-fast port scanning (feeds nmap)"),
        ("tool: masscan", WARN, "Large-scale port scanning"),
        ("tool: nuclei", OK, "Template-based vulnerability scanning"),
        ("tool: whatweb", OK, "Web technology fingerprinting"),
        ("tool: testssl.sh", WARN, "TLS configuration auditing"),
        ("mDNS (zeroconf)", OK, "IoT discovery"),
        ("Node/pnpm", OK, "pnpm 9.12.0"),
        ("Dashboard built", OK, "frontend/dist"),
        ("Database", OK, "sqlite:///data/netscan.db"),
        ("Active interfaces", OK, "eth0 (10000Mbps)"),
    ]
    for name, mark, detail in rows:
        table.add_row(name, mark, detail)
    return table


console.print()
console.print(build())
console.print()
console.save_svg(
    "docs/screenshots/doctor-cli.svg",
    title="netscan doctor",
)

# SVG -> PNG (resvg; uses DejaVu Sans Mono, present on most distros).
try:
    import resvg_py

    _svg = __import__("pathlib").Path("docs/screenshots/doctor-cli.svg").read_text()
    _png = resvg_py.svg_to_bytes(
        svg_string=_svg,
        zoom=2.0,
        font_family="DejaVu Sans Mono",
        monospace_family="DejaVu Sans Mono",
    )
    __import__("pathlib").Path("docs/screenshots/doctor-cli.png").write_bytes(bytes(_png))
    print("PNG written to docs/screenshots/doctor-cli.png")
except ImportError:
    print("resvg-py not installed: only the SVG was generated. pip install resvg-py for the PNG.")
print("SVG written to docs/screenshots/doctor-cli.svg")
