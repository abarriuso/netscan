"""Genera docs/screenshots/doctor-cli.svg reproduciendo la salida real de
`netscan doctor` con Rich (record=True → save_svg). Datos de ejemplo realistas
para que la captura sea representativa aunque no haya herramientas instaladas.

Uso:  backend/.venv-linux/bin/python docs/screenshots/_gen_doctor.py
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

console = Console(record=True, width=84)


def build() -> Table:
    table = Table(title="NetScan — diagnóstico", header_style="bold cyan")
    table.add_column("Comprobación", style="bold")
    table.add_column("Estado")
    table.add_column("Detalle", style="dim")

    OK = "[green]OK[/green]"
    WARN = "[yellow]aviso[/yellow]"

    rows = [
        ("Python", OK, "3.12.3"),
        ("Privilegios (ARP)", OK, "elevado"),
        ("tool: nmap", OK, "Service/version detection, OS fingerprinting"),
        ("tool: rustscan", OK, "Ultra-fast port scanning (feeds nmap)"),
        ("tool: masscan", WARN, "Large-scale port scanning"),
        ("tool: nuclei", OK, "Template-based vulnerability scanning"),
        ("tool: whatweb", OK, "Web technology fingerprinting"),
        ("tool: testssl.sh", WARN, "TLS configuration auditing"),
        ("mDNS (zeroconf)", OK, "descubrimiento IoT"),
        ("Node/pnpm", OK, "pnpm 9.12.0"),
        ("Dashboard compilado", OK, "frontend/dist"),
        ("Base de datos", OK, "sqlite:///data/netscan.db"),
        ("Interfaces activas", OK, "eth0 (10000Mbps)"),
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

# SVG → PNG (resvg; usa DejaVu Sans Mono, presente en la mayoría de distros).
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
    print("PNG escrito en docs/screenshots/doctor-cli.png")
except ImportError:
    print("resvg-py no instalado: solo se generó el SVG. pip install resvg-py para el PNG.")
print("SVG escrito en docs/screenshots/doctor-cli.svg")
