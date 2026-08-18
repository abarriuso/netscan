#!/usr/bin/env python3
import argparse
import asyncio
import csv
import ipaddress
import json
import os
import platform
import socket
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel
from rich.text import Text

try:
    from scapy.all import ARP, Ether, srp, conf
    conf.verbosity = 0
except ImportError:
    print("Error: scapy no está instalado. Ejecuta: pip install scapy")
    sys.exit(1)

try:
    import netifaces
except ImportError:
    netifaces = None

try:
    from mac_vendor_lookup import MacLookup
    mac_lookup = MacLookup()
    try:
        mac_lookup.update_vendors()
    except Exception:
        pass
except ImportError:
    mac_lookup = None

console = Console()

COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
    80: "HTTP", 110: "POP3", 135: "RPC", 139: "NetBIOS", 143: "IMAP",
    443: "HTTPS", 445: "SMB", 993: "IMAPS", 995: "POP3S",
    1433: "MSSQL", 1521: "Oracle", 3306: "MySQL", 3389: "RDP",
    5432: "PostgreSQL", 5900: "VNC", 6379: "Redis", 8080: "HTTP-Alt",
    8443: "HTTPS-Alt", 8888: "HTTP-Proxy", 9090: "WebUI", 27017: "MongoDB",
}

EXTENDED_PORTS = {
    161: "SNMP", 162: "SNMP-Trap", 389: "LDAP", 636: "LDAPS",
    514: "Syslog", 1883: "MQTT", 5353: "mDNS", 5355: "LLMNR",
    9100: "Printer", 631: "IPP", 49152: "UPnP",
}


def get_local_network():
    if netifaces:
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get("addr", "")
                    netmask = addr.get("netmask", "")
                    if ip and netmask and not ip.startswith("127."):
                        try:
                            network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
                            return str(network), ip, iface
                        except ValueError:
                            continue
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return f"{ip.rsplit('.', 1)[0]}.0/24", ip, "default"


def arp_scan(network_cidr):
    network = ipaddress.IPv4Network(network_cidr, strict=False)
    if network.num_addresses > 65536:
        console.print(f"[yellow]Red muy grande ({network.num_addresses} hosts). Limitando a /16.[/yellow]")
        network = ipaddress.IPv4Network(f"{network.network_address}/16", strict=False)

    arp_request = ARP(pdst=str(network))
    broadcast = Ether(dst="ff:ff:ff:ff:ff:ff")
    packet = broadcast / arp_request

    with console.status("[bold cyan]Escaneando red con ARP..."):
        result = srp(packet, timeout=3, verbose=False)

    devices = []
    for sent, received in result[0]:
        devices.append({
            "ip": received.psrc,
            "mac": received.hwsrc.lower(),
        })

    devices.sort(key=lambda d: ipaddress.IPv4Address(d["ip"]))
    return devices


def get_vendor(mac):
    if not mac_lookup:
        return "Desconocido"
    try:
        return mac_lookup.lookup(mac)
    except Exception:
        return "Desconocido"


def resolve_vendors(devices):
    """Resuelve los vendors en el hilo principal (mac_vendor_lookup no es
    thread-safe: guarda su propio event loop). Devuelve un dict MAC -> vendor."""
    cache = {}
    for dev in devices:
        mac = dev["mac"]
        if mac not in cache:
            cache[mac] = get_vendor(mac)
    return cache


def resolve_hostname(ip):
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, OSError):
        return ""


def ping_host(ip, timeout=1):
    param = "-n" if platform.system().lower() == "windows" else "-c"
    timeout_param = "-w" if platform.system().lower() == "windows" else "-W"
    timeout_val = str(timeout * 1000) if platform.system().lower() == "windows" else str(timeout)

    try:
        start = time.perf_counter()
        result = subprocess.run(
            ["ping", param, "1", timeout_param, timeout_val, ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 2
        )
        elapsed = (time.perf_counter() - start) * 1000
        if result.returncode == 0:
            return round(elapsed, 1)
    except (subprocess.TimeoutExpired, Exception):
        pass
    return None


def scan_port(ip, port, timeout=0.5):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def scan_ports(ip, ports, max_workers=50):
    open_ports = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scan_port, ip, port): port for port in ports}
        for future in as_completed(futures):
            port = futures[future]
            if future.result():
                service = ports.get(port, "unknown")
                open_ports.append((port, service))
    open_ports.sort()
    return open_ports


def detect_os_from_ports(open_ports):
    port_set = {p for p, _ in open_ports}
    if 3389 in port_set or 135 in port_set or 445 in port_set:
        return "Windows"
    if 22 in port_set and 80 in port_set and not 445 in port_set:
        return "Linux/Unix"
    if 548 in port_set or 62078 in port_set:
        return "Apple"
    return ""


def enrich_device(device, ports_to_scan, max_workers=50, skip_ports=False, skip_ping=False, vendor_cache=None):
    ip = device["ip"]

    if not skip_ping:
        device["latency_ms"] = ping_host(ip)
    else:
        device["latency_ms"] = None

    device["hostname"] = resolve_hostname(ip)
    device["vendor"] = (vendor_cache or {}).get(device["mac"]) or get_vendor(device["mac"])

    if not skip_ports:
        device["open_ports"] = scan_ports(ip, ports_to_scan, max_workers)
        device["os_guess"] = detect_os_from_ports(device["open_ports"])
    else:
        device["open_ports"] = []
        device["os_guess"] = ""

    return device


def display_results(devices, network_cidr, local_ip, iface):
    console.print()
    header = Text()
    header.append(f"Red: ", style="bold")
    header.append(f"{network_cidr}", style="cyan")
    header.append(f"  |  Interfaz: ", style="bold")
    header.append(f"{iface}", style="cyan")
    header.append(f"  |  Tu IP: ", style="bold")
    header.append(f"{local_ip}", style="green")
    header.append(f"  |  Dispositivos: ", style="bold")
    header.append(f"{len(devices)}", style="yellow")
    header.append(f"  |  Fecha: ", style="bold")
    header.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", style="magenta")

    console.print(Panel(header, title="[bold]NetScan - Resultados[/bold]", border_style="blue"))
    console.print()

    table = Table(show_header=True, header_style="bold cyan", border_style="dim", expand=True)
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("IP", style="bold white", min_width=15)
    table.add_column("MAC", style="dim", min_width=17)
    table.add_column("Hostname", style="green", min_width=15)
    table.add_column("Vendor", style="yellow", min_width=15)
    table.add_column("Latencia", justify="right", min_width=8)
    table.add_column("OS", style="magenta", min_width=10)
    table.add_column("Puertos Abiertos", style="red", min_width=30)

    for i, dev in enumerate(devices, 1):
        is_local = "bold green" if dev["ip"] == local_ip else ""

        latency = f"{dev['latency_ms']}ms" if dev.get("latency_ms") else "[dim]-[/dim]"
        hostname = dev.get("hostname", "") or "[dim]-[/dim]"
        vendor = dev.get("vendor", "") or "[dim]-[/dim]"
        os_guess = dev.get("os_guess", "") or "[dim]-[/dim]"

        ports_str = ""
        if dev.get("open_ports"):
            parts = []
            for port, service in dev["open_ports"]:
                parts.append(f"{port}({service})")
            ports_str = ", ".join(parts)
        else:
            ports_str = "[dim]-[/dim]"

        marker = " *" if dev["ip"] == local_ip else ""
        table.add_row(
            str(i),
            f"[{is_local}]{dev['ip']}{marker}[/{is_local}]" if is_local else f"{dev['ip']}{marker}",
            dev["mac"],
            hostname,
            vendor,
            latency,
            os_guess,
            ports_str,
        )

    console.print(table)
    console.print()


def export_json(devices, filepath):
    output = {
        "scan_time": datetime.now().isoformat(),
        "total_devices": len(devices),
        "devices": devices,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    console.print(f"[green]Exportado a {filepath}[/green]")


def export_csv(devices, filepath):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["IP", "MAC", "Hostname", "Vendor", "Latencia (ms)", "OS", "Puertos Abiertos"])
        for dev in devices:
            ports = ", ".join(f"{p}({s})" for p, s in dev.get("open_ports", []))
            writer.writerow([
                dev["ip"],
                dev["mac"],
                dev.get("hostname", ""),
                dev.get("vendor", ""),
                dev.get("latency_ms", ""),
                dev.get("os_guess", ""),
                ports,
            ])
    console.print(f"[green]Exportado a {filepath}[/green]")


def parse_args():
    parser = argparse.ArgumentParser(
        description="NetScan - Escáner de red para gestión de homelab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python netscan.py                          Escaneo rápido de la red local
  python netscan.py --full                   Escaneo completo con puertos
  python netscan.py -n 192.168.1.0/24        Escanear red específica
  python netscan.py --full --export json     Escaneo completo + exportar JSON
  python netscan.py --quick                  Solo ARP + hostname (sin puertos ni ping)
  python netscan.py --ports 22,80,443,8080   Puertos personalizados
        """
    )

    parser.add_argument("-n", "--network", help="Red a escanear en formato CIDR (ej: 192.168.1.0/24)")
    parser.add_argument("--quick", action="store_true", help="Escaneo rápido: solo ARP + hostname")
    parser.add_argument("--full", action="store_true", help="Escaneo completo con todos los puertos comunes")
    parser.add_argument("--no-ping", action="store_true", help="Omitir ping (latencia)")
    parser.add_argument("--no-ports", action="store_true", help="Omitir escaneo de puertos")
    parser.add_argument("--ports", help="Lista de puertos personalizados separados por coma (ej: 22,80,443)")
    parser.add_argument("--export", choices=["json", "csv", "both"], help="Exportar resultados")
    parser.add_argument("-o", "--output", help="Nombre base del archivo de salida (sin extensión)")
    parser.add_argument("-w", "--workers", type=int, default=50, help="Hilos para escaneo de puertos (default: 50)")
    parser.add_argument("-t", "--timeout", type=float, default=0.5, help="Timeout por puerto en segundos (default: 0.5)")

    return parser.parse_args()


def main():
    args = parse_args()

    console.print(Panel.fit(
        "[bold cyan]NetScan[/bold cyan]\n"
        "[dim]Escáner de red para gestión de homelab[/dim]",
        border_style="blue"
    ))

    if args.network:
        try:
            network = ipaddress.IPv4Network(args.network, strict=False)
            network_cidr = str(network)
        except ValueError:
            console.print(f"[red]Red inválida: {args.network}[/red]")
            sys.exit(1)
        local_ip = ""
        iface = "custom"
    else:
        network_cidr, local_ip, iface = get_local_network()

    console.print(f"[dim]Red objetivo: [cyan]{network_cidr}[/cyan][/dim]")
    console.print(f"[dim]Interfaz: [cyan]{iface}[/cyan][/dim]")
    if local_ip:
        console.print(f"[dim]Tu IP: [green]{local_ip}[/green][/dim]")
    console.print()

    devices = arp_scan(network_cidr)

    if not devices:
        console.print("[red]No se encontraron dispositivos en la red.[/red]")
        console.print("[yellow]Asegúrate de ejecutar con privilegios de administrador.[/yellow]")
        sys.exit(1)

    console.print(f"[green]Encontrados {len(devices)} dispositivos.[/green] Enriqueciendo datos...\n")

    if args.quick:
        skip_ports = True
        skip_ping = True
        ports_to_scan = {}
    else:
        skip_ports = args.no_ports
        skip_ping = args.no_ping

        if args.ports:
            custom_ports = {}
            for p in args.ports.split(","):
                p = int(p.strip())
                custom_ports[p] = f"port-{p}"
            ports_to_scan = custom_ports
        elif args.full:
            ports_to_scan = {**COMMON_PORTS, **EXTENDED_PORTS}
        else:
            ports_to_scan = COMMON_PORTS

    vendor_cache = resolve_vendors(devices)

    enriched = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task = progress.add_task("Escaneando dispositivos...", total=len(devices))
        with ThreadPoolExecutor(max_workers=min(args.workers, len(devices))) as executor:
            futures = {
                executor.submit(enrich_device, dev, ports_to_scan, args.workers, skip_ports, skip_ping, vendor_cache): dev
                for dev in devices
            }
            for future in as_completed(futures):
                result = future.result()
                enriched.append(result)
                progress.advance(task)

    enriched.sort(key=lambda d: ipaddress.IPv4Address(d["ip"]))

    display_results(enriched, network_cidr, local_ip, iface)

    if args.export:
        base_name = args.output or f"netscan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if args.export in ("json", "both"):
            export_json(enriched, f"{base_name}.json")
        if args.export in ("csv", "both"):
            export_csv(enriched, f"{base_name}.csv")


if __name__ == "__main__":
    main()
