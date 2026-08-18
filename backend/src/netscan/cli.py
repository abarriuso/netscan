"""NetScan CLI.

Copyright (C) 2026 The NetScan contributors.
SPDX-License-Identifier: GPL-2.0-or-later
"""

from __future__ import annotations

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
def serve(
    host: str | None = typer.Option(None, help="Host de escucha de la API"),
    port: int | None = typer.Option(None, help="Puerto de la API"),
) -> None:
    """Lanza el servidor API + scheduler de monitorización."""
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "netscan.api.app:create_app",
        factory=True,
        host=host or settings.api_host,
        port=port or settings.api_port,
    )


if __name__ == "__main__":
    app()
