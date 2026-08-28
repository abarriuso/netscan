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
    help="NetScan — escáner de red, inventario y monitorización de homelab.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def scan(
    network: str | None = typer.Option(None, "-n", "--network", help="Red CIDR (ej: 192.168.1.0/24)"),
    full: bool = typer.Option(False, "--full", help="Escaneo completo con puertos extendidos"),
    quick: bool = typer.Option(False, "--quick", help="Solo ARP + hostname"),
    export: str | None = typer.Option(None, "--export", help="json | csv | both"),
    output: str | None = typer.Option(None, "-o", "--output", help="Nombre base de salida"),
    save: bool = typer.Option(False, "--save", help="Guardar en el inventario SQLite"),
) -> None:
    """Escanea la red y muestra los dispositivos encontrados."""
    console.print(
        Panel.fit(
            f"[bold cyan]NetScan v{__version__}[/bold cyan]\n[dim]Escáner de red y monitor de homelab[/dim]",
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
        task = progress.add_task("Iniciando...", total=1)

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
        console.print("[red]No se encontraron dispositivos.[/red]")
        console.print("[yellow]¿Ejecutas con privilegios de administrador?[/yellow]")
        raise typer.Exit(1)
    if save:
        from netscan.db.store import InventoryStore

        settings = load_settings()
        store = InventoryStore(settings.db_url, str(settings.data_dir))
        alerts = store.record_scan(result)
        for alert in alerts:
            console.print(f"[bold yellow]ALERTA:[/bold yellow] {alert.detail}")


def _display(result: ScanResult) -> None:
    console.print()
    header = Text()
    header.append("Red: ", style="bold")
    header.append(f"{result.network}", style="cyan")
    header.append("  |  Dispositivos: ", style="bold")
    header.append(f"{result.total_devices}", style="yellow")
    header.append("  |  Duración: ", style="bold")
    header.append(f"{result.duration_s}s", style="magenta")
    console.print(Panel(header, title="[bold]NetScan — Resultados[/bold]", border_style="blue"))

    table = Table(show_header=True, header_style="bold cyan", border_style="dim", expand=True)
    for col, style in (
        ("IP", "bold white"),
        ("MAC", "dim"),
        ("Hostname", "green"),
        ("Vendor", "yellow"),
        ("Latencia", ""),
        ("OS", "magenta"),
        ("Puertos", "red"),
        ("Servicios", "blue"),
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
        console.print("[bold red]Hallazgos nuclei:[/bold red]")
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
        console.print(f"[green]Exportado a {base}.json[/green]")
    if export in ("csv", "both"):
        with open(f"{base}.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["IP", "MAC", "Hostname", "Vendor", "Latencia (ms)", "OS", "Puertos"])
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
        console.print(f"[green]Exportado a {base}.csv[/green]")


@app.command()
def caps() -> None:
    """Muestra las herramientas externas disponibles en este equipo."""
    capabilities = tools.Capabilities.detect()
    table = Table(title="Capacidades detectadas", header_style="bold cyan")
    table.add_column("Herramienta", style="bold")
    table.add_column("Licencia", style="dim")
    table.add_column("Disponible")
    table.add_column("Propósito", style="dim")
    for key, spec in tools.TOOLS.items():
        available = capabilities.tools.get(key, False)
        table.add_row(
            spec.name,
            spec.license,
            "[green]sí[/green]" if available else "[dim]no[/dim]",
            spec.purpose,
        )
    table.add_row(
        "zeroconf (mDNS)",
        "LGPL-2.1",
        "[green]sí[/green]" if capabilities.mdns else "[dim]no[/dim]",
        "Descubrimiento de IoT vía mDNS/Bonjour",
    )
    console.print(table)


@app.command()
def wake(
    mac: str = typer.Argument(..., help="MAC del equipo a despertar (aa:bb:cc:dd:ee:ff)"),
    broadcast: str = typer.Option("255.255.255.255", help="Dirección de broadcast"),
) -> None:
    """Envía un magic packet Wake-on-LAN."""
    from netscan import wol

    try:
        wol.wake(mac, broadcast)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Magic packet enviado a {mac}[/green]")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Host de escucha de la API"),
    port: int | None = typer.Option(None, help="Puerto de la API"),
) -> None:
    """Lanza solo el servidor API + scheduler de monitorización (sin abrir navegador)."""
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
    npm = shutil.which("npm")
    if not npm:
        console.print("[yellow]npm no encontrado: sirvo la API sin el dashboard integrado.[/yellow]")
        return (dist / "index.html").is_file()
    if not (frontend / "node_modules").is_dir():
        console.print("[cyan]Instalando dependencias del dashboard (npm install)...[/cyan]")
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=frontend, check=False)
    console.print("[cyan]Compilando el dashboard (npm run build)...[/cyan]")
    proc = subprocess.run([npm, "run", "build"], cwd=frontend, check=False)
    return proc.returncode == 0 and (dist / "index.html").is_file()


@app.command()
def up(
    host: str | None = typer.Option(None, help="Host de escucha"),
    port: int | None = typer.Option(None, help="Puerto"),
    build: bool = typer.Option(False, "--build", help="Forzar recompilar el dashboard"),
    no_browser: bool = typer.Option(False, "--no-browser", help="No abrir el navegador"),
) -> None:
    """Arranca TODO en un solo comando: API + dashboard integrado + navegador."""
    import threading
    import time as _time
    import webbrowser

    import uvicorn

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
                "[dim]dashboard integrado servido por el backend[/dim]"
                if built
                else "[yellow]dashboard no compilado — solo API disponible[/yellow]"
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
    target: str | None = typer.Argument(None, help="IP concreta (por defecto: toda la red)"),
    network: str | None = typer.Option(None, "-n", "--network", help="Red CIDR"),
    pings: int = typer.Option(5, help="Número de pings por dispositivo"),
    throughput: bool = typer.Option(False, "--throughput", help="Medir ancho de banda real (más lento)"),
) -> None:
    """Mide latencia, jitter, pérdida, handshake TCP y throughput por dispositivo."""
    from netscan.scanner import enrich, speed

    console.print(
        Panel.fit(
            "[bold cyan]NetScan speed test[/bold cyan]\n[dim]latencia · jitter · pérdida · TCP · throughput[/dim]",
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
            console.print("[red]No se encontraron dispositivos.[/red]")
            raise typer.Exit(1)

    ports = {**enrich.COMMON_PORTS, **enrich.EXTENDED_PORTS}
    table = Table(show_header=True, header_style="bold cyan", border_style="dim", expand=True)
    for col in ("IP", "Latencia", "Jitter", "Pérdida", "TCP medio", "Throughput", "Calidad"):
        table.add_column(col)

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        task = progress.add_task("Midiendo...", total=len(targets))
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
    """Diagnóstico completo: Python, herramientas, dashboard, privilegios y red."""
    import shutil

    from netscan import system
    from netscan.scanner import discovery

    settings = load_settings()

    table = Table(title="NetScan — diagnóstico", header_style="bold cyan")
    table.add_column("Comprobación", style="bold")
    table.add_column("Estado")
    table.add_column("Detalle", style="dim")

    def row(name: str, ok: bool | None, detail: str) -> None:
        mark = "[green]OK[/green]" if ok else ("[yellow]aviso[/yellow]" if ok is None else "[red]falta[/red]")
        table.add_row(name, mark, detail)

    import sys

    py_ok = sys.version_info >= (3, 11)
    row("Python", py_ok, sys.version.split()[0])
    row(
        "Privilegios (ARP)",
        discovery.is_elevated() or None,
        "elevado" if discovery.is_elevated() else "sin privilegios — el ARP scan requiere admin/sudo",
    )

    caps = tools.Capabilities.detect()
    for key, spec in tools.TOOLS.items():
        available = caps.tools.get(key, False)
        row(f"tool: {spec.name}", available or None, spec.purpose)
    row("mDNS (zeroconf)", caps.mdns or None, "descubrimiento IoT")

    row(
        "Node/npm",
        shutil.which("npm") is not None or None,
        shutil.which("npm") or "necesario solo para compilar el dashboard",
    )

    fe = system.frontend_status()
    row(
        "Dashboard compilado",
        bool(fe.get("built")) or None,
        str(fe.get("path")) if fe.get("built") else "ejecuta: netscan up --build",
    )

    row("Base de datos", True, settings.db_url)

    net = system.network_info()
    ifaces = net.get("interfaces")
    if not isinstance(ifaces, list):
        ifaces = []
    up_ifaces = [i for i in ifaces if isinstance(i, dict) and i.get("is_up")]
    row(
        "Interfaces activas",
        bool(up_ifaces) or None,
        ", ".join(f"{i['name']} ({i.get('speed_mbps') or '?'}Mbps)" for i in up_ifaces[:4]) or "ninguna",
    )

    console.print(table)


if __name__ == "__main__":
    app()
