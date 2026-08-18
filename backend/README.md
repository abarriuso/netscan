# netscan-homelab (backend)

Motor de escaneo de red, inventario persistente y API de monitorización para
homelab, con integración de Proxmox VE, TrueNAS y AdGuard Home.

Parte del monorepo [NetScan](../README.md). Licencia: GPL-2.0-or-later.

```bash
pip install -e ".[dev]"
netscan scan --full          # CLI
netscan caps                 # herramientas externas detectadas
netscan serve                # API en :8600 + scheduler
pytest                       # tests
```
