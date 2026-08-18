# Arquitectura

## Visión general

```
┌────────────┐   REST/WS    ┌─────────────────────────────────────┐
│  frontend  │ ◄──────────► │  FastAPI (netscan.api.app)          │
│  React+Vite│              │   ├─ routes: scans/devices/alerts   │
└────────────┘              │   ├─ WS /ws/progress                │
                            │   └─ scheduler (escaneo periódico)  │
┌────────────┐              └──────┬──────────────────────────────┘
│  CLI typer│ ────────────────────►│ engine.run_scan()             │
└────────────┘                     │   ├─ discovery.arp_scan (scapy)│
                                   │   ├─ mdns.mdns_discover        │
                                   │   ├─ enrich (ping/ports/OUI)   │
                                   │   ├─ fingerprint (HTTP/TLS)    │
                                   │   └─ tools (nmap, nuclei…)     │
                                   ├─ InventoryStore (SQLite)      │
                                   │   └─ diff → AlertRecord        │
                                   ├─ integrations/                 │
                                   │   proxmox · truenas · adguard  │
                                   └─ alerts.notify (Apprise)      │
```

## Decisiones clave

- **Un solo `engine.run_scan()`** sirve a la CLI y a la API. El progreso se
  emite con un callback `(stage, done, total)` que la CLI pinta con rich y la
  API reenvía por WebSocket.
- **Pasos no thread-safe en el hilo principal**: OUI lookup
  (mac_vendor_lookup) y mDNS se resuelven antes del pool de hilos; el
  enriquecimiento por dispositivo sí es concurrente.
- **Diff de inventario por MAC**: la MAC es la clave estable; un cambio de IP
  genera alerta `mac_changed`; una MAC desconocida, `new_device`.
- **Herramientas externas opcionales**: `scanner/tools.py` detecta binarios
  con `shutil.which`, expone `Capabilities` a la API (`/api/capabilities`) y
  cada wrapper devuelve `None`/vacío si falta la herramienta. Nada falla por
  no tener nmap instalado.
- **Integraciones tolerantes a fallos**: `collect_all()` captura cualquier
  excepción por instancia y la devuelve como `{"error": ...}` — un Proxmox
  apagado no tumba el dashboard.
- **Secretos fuera del repo**: pydantic-settings mezcla YAML + env; los
  tokens viven en variables `NETSCAN_*`.

## Extensiones previstas

- `scanner/tools.py`: wrappers adicionales (RustScan → nmap, nuclei contra
  web UIs detectadas) — la infraestructura de capacidades ya está.
- SNMP (puerto 161) vía consulta directa o NSE de nmap.
- Wake-on-LAN: las MACs ya están en el inventario.
- Historial de latencia para gráficas (los ScanRecord ya guardan series).
