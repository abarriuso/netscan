"""NetScan CLI.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

import contextlib
import csv
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from netscan import __version__
from netscan.config import load_settings
from netscan.models import ScanResult
from netscan.scanner import engine, tools

app = typer.Typer(
    name="netscan",
    help="NetScan — network scanner, inventory and monitoring for homelabs.",
    no_args_is_help=True,
)
console = Console()

# Shocking pink — the one loud accent NetScan allows itself, reserved for
# this startup banner (the dashboard itself stays sober; see index.css).
_BANNER_PINK = "bold #FC0FC0"


def _print_banner() -> None:
    """Big ASCII-art banner for the flagship `up` command."""
    import pyfiglet

    banner = pyfiglet.figlet_format("NETSCAN", font="3-d", width=200)
    console.print(Text(banner, style=_BANNER_PINK))


@app.command()
def scan(
    network: str | None = typer.Option(None, "-n", "--network", help="CIDR network (e.g. 192.168.1.0/24)"),
    full: bool = typer.Option(False, "--full", help="Full scan with extended ports"),
    quick: bool = typer.Option(False, "--quick", help="ARP + hostname only"),
    export: str | None = typer.Option(None, "--export", help="json | csv | both"),
    output: str | None = typer.Option(None, "-o", "--output", help="Output base name"),
    save: bool = typer.Option(False, "--save", help="Save to the SQLite inventory"),
) -> None:
    """Scan the network and show the devices found."""
    console.print(
        Panel.fit(
            f"[bold cyan]NetScan v{__version__}[/bold cyan]\n[dim]Network scanner and homelab monitor[/dim]",
            border_style="blue",
        )
    )

    cfg = load_settings().scan
    if quick:
        cfg.use_mdns = False
        cfg.use_fingerprint = False
        cfg.use_nmap = False

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("Starting...", total=1)

        def on_progress(stage: str, done: int, total: int) -> None:
            progress.update(task, description=f"[cyan]{stage}[/cyan]", total=max(total, 1))
            progress.update(task, completed=done)

        result = engine.run_scan(cfg=cfg, network=network, full=full or None, progress=on_progress)

    if save or result.total_devices == 0:
        _persist(result, save)
    _display(result)
    if export:
        _export(result, export, output)


def _persist(result: ScanResult, save: bool) -> None:
    if result.total_devices == 0:
        console.print("[red]No devices found.[/red]")
        console.print("[yellow]Are you running with administrator privileges?[/yellow]")
        raise typer.Exit(1)
    if save:
        from netscan.db.store import InventoryStore

        settings = load_settings()
        store = InventoryStore(settings.db_url, str(settings.data_dir))
        alerts = store.record_scan(result)
        for alert in alerts:
            console.print(f"[bold yellow]ALERT:[/bold yellow] {alert.detail}")


def _display(result: ScanResult) -> None:
    console.print()
    header = Text()
    header.append("Network: ", style="bold")
    header.append(f"{result.network}", style="cyan")
    header.append("  |  Devices: ", style="bold")
    header.append(f"{result.total_devices}", style="yellow")
    header.append("  |  Duration: ", style="bold")
    header.append(f"{result.duration_s}s", style="magenta")
    console.print(Panel(header, title="[bold]NetScan — Results[/bold]", border_style="blue"))

    table = Table(show_header=True, header_style="bold cyan", border_style="dim", expand=True)
    for col, style in (
        ("IP", "bold white"),
        ("MAC", "dim"),
        ("Hostname", "green"),
        ("Vendor", "yellow"),
        ("Latency", ""),
        ("OS", "magenta"),
        ("Ports", "red"),
        ("Services", "blue"),
    ):
        table.add_column(col, style=style, min_width=8)

    for dev in result.devices:
        ports = ", ".join(f"{p.port}({p.service})" for p in dev.open_ports) or "[dim]-[/dim]"
        services = ", ".join(dev.mdns_services) or "[dim]-[/dim]"
        latency = f"{dev.latency_ms}ms" if dev.latency_ms is not None else "[dim]-[/dim]"
        table.add_row(
            dev.ip,
            dev.mac,
            dev.hostname or dev.mdns_name or "[dim]-[/dim]",
            dev.vendor or "[dim]-[/dim]",
            latency,
            dev.os_guess or "[dim]-[/dim]",
            ports,
            services,
        )
    console.print(table)
    if result.vulnerabilities:
        console.print()
        console.print("[bold red]nuclei findings:[/bold red]")
        for finding in result.vulnerabilities:
            console.print(
                f"  [red]{finding.get('severity', '?')}[/red] "
                f"{finding.get('name', finding.get('template', ''))} "
                f"[dim]→ {finding.get('matched_at', '')}[/dim]"
            )


def _export(result: ScanResult, export: str, output: str | None) -> None:
    from datetime import datetime

    base = output or f"netscan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if export in ("json", "both"):
        Path(f"{base}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]Exported to {base}.json[/green]")
    if export in ("csv", "both"):
        with open(f"{base}.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["IP", "MAC", "Hostname", "Vendor", "Latency (ms)", "OS", "Ports"])
            for dev in result.devices:
                writer.writerow(
                    [
                        dev.ip,
                        dev.mac,
                        dev.hostname,
                        dev.vendor,
                        dev.latency_ms or "",
                        dev.os_guess,
                        ", ".join(f"{p.port}({p.service})" for p in dev.open_ports),
                    ]
                )
        console.print(f"[green]Exported to {base}.csv[/green]")


@app.command()
def caps() -> None:
    """Show the external tools available on this machine."""
    capabilities = tools.Capabilities.detect()
    table = Table(title="Detected capabilities", header_style="bold cyan")
    table.add_column("Tool", style="bold")
    table.add_column("Licence", style="dim")
    table.add_column("Available")
    table.add_column("Purpose", style="dim")
    for key, spec in tools.TOOLS.items():
        available = capabilities.tools.get(key, False)
        table.add_row(
            spec.name,
            spec.license,
            "[green]yes[/green]" if available else "[dim]no[/dim]",
            spec.purpose,
        )
    table.add_row(
        "zeroconf (mDNS)",
        "LGPL-2.1",
        "[green]yes[/green]" if capabilities.mdns else "[dim]no[/dim]",
        "IoT discovery through mDNS/Bonjour",
    )
    console.print(table)


@app.command()
def wake(
    mac: str = typer.Argument(..., help="MAC of the machine to wake (aa:bb:cc:dd:ee:ff)"),
    broadcast: str = typer.Option("255.255.255.255", help="Broadcast address"),
) -> None:
    """Send a Wake-on-LAN magic packet."""
    from netscan import wol

    try:
        wol.wake(mac, broadcast)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Magic packet sent to {mac}[/green]")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="API listen host"),
    port: int | None = typer.Option(None, help="API port"),
) -> None:
    """Start only the API server + monitoring scheduler (no browser)."""
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "netscan.api.app:create_app",
        factory=True,
        host=host or settings.api_host,
        port=port or settings.api_port,
    )


def _repo_root() -> Path:
    """Best-effort path to the repository root (holds the frontend/ dir)."""
    here = Path(__file__).resolve()
    # backend/src/netscan/cli.py -> parents[3] == repo root
    for cand in (here.parents[3], Path.cwd()):
        if (cand / "frontend").is_dir():
            return cand
    return here.parents[3]


def _ensure_frontend_built(build: bool) -> bool:
    """Return True if frontend/dist exists; optionally build it first."""
    import shutil
    import subprocess

    root = _repo_root()
    frontend = root / "frontend"
    dist = frontend / "dist"
    if (dist / "index.html").is_file() and not build:
        return True
    if not frontend.is_dir():
        return False
    import os

    if shutil.which("pnpm"):
        pm = ["pnpm"]
    elif shutil.which("corepack"):
        pm = ["corepack", "pnpm"]
    else:
        pm = None
    if pm is None:
        console.print(
            "[yellow]pnpm/corepack not found: serving the API without the built-in dashboard.[/yellow]"
        )
        return (dist / "index.html").is_file()
    env = {**os.environ, "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0"}
    if not (frontend / "node_modules").is_dir():
        console.print("[cyan]Installing the dashboard dependencies (pnpm install)...[/cyan]")
        subprocess.run([*pm, "install"], cwd=frontend, check=False, env=env)
    console.print("[cyan]Building the dashboard (pnpm run build)...[/cyan]")
    proc = subprocess.run([*pm, "run", "build"], cwd=frontend, check=False, env=env)
    return proc.returncode == 0 and (dist / "index.html").is_file()


@app.command()
def up(
    host: str | None = typer.Option(None, help="Listen host"),
    port: int | None = typer.Option(None, help="Port"),
    build: bool = typer.Option(False, "--build", help="Force a dashboard rebuild"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open the browser"),
) -> None:
    """Start EVERYTHING in one command: API + built-in dashboard + browser."""
    import threading
    import time as _time
    import webbrowser

    import uvicorn

    _print_banner()
    settings = load_settings()
    listen_host = host or settings.api_host
    listen_port = port or settings.api_port
    url_host = "localhost" if listen_host in ("0.0.0.0", "127.0.0.1", "") else listen_host
    url = f"http://{url_host}:{listen_port}/"

    built = _ensure_frontend_built(build)
    console.print(
        Panel.fit(
            f"[bold cyan]NetScan v{__version__}[/bold cyan]\n"
            f"[green]Dashboard:[/green] {url}\n"
            f"[green]API:[/green] {url}api/\n"
            + (
                "[dim]built-in dashboard served by the backend[/dim]"
                if built
                else "[yellow]dashboard not built — API only[/yellow]"
            ),
            title="[bold]NetScan up[/bold]",
            border_style="blue",
        )
    )

    if not no_browser and built:

        def _open() -> None:
            _time.sleep(1.5)
            with contextlib.suppress(Exception):
                webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        "netscan.api.app:create_app",
        factory=True,
        host=listen_host,
        port=listen_port,
    )


@app.command()
def speedtest(
    target: str | None = typer.Argument(None, help="A specific IP (default: the whole network)"),
    network: str | None = typer.Option(None, "-n", "--network", help="CIDR network"),
    pings: int = typer.Option(5, help="Number of pings per device"),
    throughput: bool = typer.Option(False, "--throughput", help="Measure real bandwidth (slower)"),
) -> None:
    """Measure latency, jitter, loss, TCP handshake and throughput per device."""
    from netscan.scanner import enrich, speed

    console.print(
        Panel.fit(
            "[bold cyan]NetScan speed test[/bold cyan]\n[dim]latency · jitter · loss · TCP · throughput[/dim]",
            border_style="blue",
        )
    )

    if target:
        targets = [target]
    else:
        cfg = load_settings().scan
        cfg.use_speedtest = False  # discovery only; we run metrics ourselves
        result = engine.run_scan(cfg=cfg, network=network)
        targets = [d.ip for d in result.devices]
        if not targets:
            console.print("[red]No devices found.[/red]")
            raise typer.Exit(1)

    ports = {**enrich.COMMON_PORTS, **enrich.EXTENDED_PORTS}
    table = Table(show_header=True, header_style="bold cyan", border_style="dim", expand=True)
    for col in ("IP", "Latency", "Jitter", "Loss", "Mean TCP", "Throughput", "Quality"):
        table.add_column(col)

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        task = progress.add_task("Measuring...", total=len(targets))
        for ip in targets:
            open_ports = enrich.scan_ports(ip, ports, max_workers=32, timeout=0.4)
            m = speed.measure_device(ip, open_ports, count=pings, throughput=throughput)
            q = m.quality or 0
            q_style = "green" if q >= 80 else "yellow" if q >= 50 else "red"
            table.add_row(
                ip,
                f"{m.latency_avg_ms} ms" if m.latency_avg_ms is not None else "[dim]-[/dim]",
                f"{m.jitter_ms} ms" if m.jitter_ms is not None else "[dim]-[/dim]",
                f"{m.packet_loss_pct}%" if m.packet_loss_pct is not None else "[dim]-[/dim]",
                f"{m.tcp_connect_avg_ms} ms" if m.tcp_connect_avg_ms is not None else "[dim]-[/dim]",
                f"{m.throughput_mbps} Mbps" if m.throughput_mbps is not None else "[dim]-[/dim]",
                f"[{q_style}]{q}/100[/{q_style}]",
            )
            progress.advance(task)
    console.print(table)


@app.command()
def doctor() -> None:
    """Full diagnosis: Python, tools, dashboard, privileges and network."""
    import shutil

    from netscan import system
    from netscan.scanner import discovery

    settings = load_settings()

    table = Table(title="NetScan — diagnosis", header_style="bold cyan")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail", style="dim")

    def row(name: str, ok: bool | None, detail: str) -> None:
        mark = (
            "[green]OK[/green]"
            if ok
            else ("[yellow]warning[/yellow]" if ok is None else "[red]missing[/red]")
        )
        table.add_row(name, mark, detail)

    import sys

    py_ok = sys.version_info >= (3, 11)
    row("Python", py_ok, sys.version.split()[0])
    row(
        "Privileges (ARP)",
        discovery.is_elevated() or None,
        "elevated" if discovery.is_elevated() else "not elevated — the ARP scan needs admin/sudo",
    )

    caps = tools.Capabilities.detect()
    for key, spec in tools.TOOLS.items():
        available = caps.tools.get(key, False)
        row(f"tool: {spec.name}", available or None, spec.purpose)
    row("mDNS (zeroconf)", caps.mdns or None, "IoT discovery")

    row(
        "Node/pnpm",
        (shutil.which("pnpm") or shutil.which("corepack")) is not None or None,
        shutil.which("pnpm") or shutil.which("corepack") or "only needed to build the dashboard",
    )

    fe = system.frontend_status()
    row(
        "Dashboard built",
        bool(fe.get("built")) or None,
        str(fe.get("path")) if fe.get("built") else "run: netscan up --build",
    )

    row("Database", True, settings.db_url)

    net = system.network_info()
    ifaces = net.get("interfaces")
    if not isinstance(ifaces, list):
        ifaces = []
    up_ifaces = [i for i in ifaces if isinstance(i, dict) and i.get("is_up")]
    row(
        "Active interfaces",
        bool(up_ifaces) or None,
        ", ".join(f"{i['name']} ({i.get('speed_mbps') or '?'}Mbps)" for i in up_ifaces[:4]) or "none",
    )

    console.print(table)


if __name__ == "__main__":
    app()
