# netscan-homelab (backend)

Network scanning engine, persistent inventory and monitoring API for homelabs,
with Proxmox VE, TrueNAS and AdGuard Home integrations.

Part of the [NetScan](../README.md) monorepo. Licence: GPL-2.0-or-later.

```bash
pip install -e ".[dev]"
netscan scan --full          # CLI
netscan caps                 # detected external tools
netscan serve                # API on :8600 + scheduler
pytest                       # tests
```
