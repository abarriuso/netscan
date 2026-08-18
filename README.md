# NetScan — Homelab Network & Systems Monitor

[![CI](https://github.com/abarriuso/netscan/actions/workflows/ci.yml/badge.svg)](https://github.com/abarriuso/netscan/actions/workflows/ci.yml)
[![License: GPL v2+](https://img.shields.io/badge/license-GPL--2.0--or--later-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

Escáner de red, inventario vivo y panel de monitorización para homelabs, con
integración directa de **Proxmox VE**, **TrueNAS** y **AdGuard Home**.

> Del escaneo puntual al vigilante permanente: descubre tu red, detecta
> intrusos, vigila tus hipervisores y tu NAS — todo en un solo dashboard.

```
┌──────────────────────────────────────────────────────────────┐
│  backend/   Python 3.11+ · FastAPI · SQLite · scapy          │
│  frontend/  React 19 · TypeScript · Vite · Tailwind · shadcn │
│  CI/CD      GitHub Actions (lint · mypy · pytest · build)    │
│  Licencia   GPL-2.0-or-later                                 │
└──────────────────────────────────────────────────────────────┘
```

## Qué hace

**Descubrimiento y fingerprinting**
- ARP scan (scapy) con lookup de vendor por OUI
- mDNS/Bonjour (zeroconf) para nombrar IoT que no responden a DNS inverso
- Escaneo de puertos multihilo + heurística de OS
- Fingerprint HTTP/TLS de las web UIs: título, `Server`, emisor del
  certificado, caducidad y autofirmados
- Integración opcional de herramientas externas con **detección automática y
  degradación elegante**: `nmap -sV` para versiones reales de servicio,
  RustScan, nuclei, whatweb, testssl.sh (ver [Licencias](#licencias))

**Inventario vivo (SQLite)**
- Cada escaneo se compara con el inventario persistido
- Alertas de **dispositivo nuevo** (detección de intrusos casera), cambio de
  IP↔MAC y dispositivo caído
- Marca dispositivos como "de confianza" desde el dashboard
- Notificaciones vía Apprise: ntfy, Telegram, Discord y +80 servicios

**Integraciones homelab**
- **Proxmox VE** (múltiples nodos/clusters): estado de nodos, VMs y CTs
- **TrueNAS** CORE/SCALE: pools, discos, SMART, alertas del sistema
- **AdGuard Home**: consultas DNS, bloqueos, clientes (cruzable con el
  inventario de red)

**Dashboard**
- Tabla densa de dispositivos con puertos, tooltips de versión y filtrado
- Paneles de Proxmox/TrueNAS/AdGuard con salud de pools y guests
- Progreso de escaneo en vivo por WebSocket
- Feed de alertas con acknowledge

## Arranque rápido

**Windows — un solo comando:**

```bat
install.bat
```

Instala el backend (venv + CLI + API), las herramientas externas vía winget
(nmap, RustScan, nuclei, Npcap) y las dependencias del dashboard. Si falta
Python o Node.js, los instala vía winget y te pedirá re-ejecutar el script.
`install.bat --minimal` instala solo backend + frontend. Después:

```bat
netscan.bat serve                          # API + scheduler (auto-elevado)
cd frontend && npm run dev                 # dashboard en :3000
```

**Linux / manual:**

```bash
# 1. Backend
python -m venv backend/.venv
backend/.venv/Scripts/pip install -e "backend[dev]"   # Windows
# backend/.venv/bin/pip install -e "backend[dev]"     # Linux

# 2. Configuración (opcional pero recomendada)
cp netscan.example.yaml netscan.yaml   # edita tus instancias Proxmox/TrueNAS

# 3. CLI
netscan scan --full      # escaneo completo
netscan caps             # herramientas externas detectadas

# 4. Servidor API + scheduler (escaneo periódico)
netscan serve            # http://localhost:8600

# 5. Dashboard
cd frontend && npm install && npm run dev   # http://localhost:3000
```

En Windows puedes usar `netscan.bat` (se auto-eleva a Administrador, necesario
para el ARP scan).

### Docker

```bash
cp netscan.example.yaml netscan.yaml
docker compose up --build
# API en :8600, dashboard en :8601
```

## Configuración

Toda la configuración vive en `netscan.yaml` (ver `netscan.example.yaml`) y
puede sobreescribirse con variables de entorno `NETSCAN_*`:

```bash
NETSCAN_PROXMOX__0__TOKEN_SECRET=xxxx   # secreto del token de pve1
NETSCAN_TRUENAS__0__API_KEY=xxxx
NETSCAN_NOTIFY_URLS__0=ntfy://ntfy.sh/mi-topic
```

**Nunca** subas secretos al repo: el YAML está git-ignored solo si lo nombras
`config.local.yaml`; los secretos deben ir siempre en variables de entorno.

### Credenciales necesarias

| Servicio | Qué crear | Dónde |
|---|---|---|
| Proxmox VE | API Token (`PVEAPIToken`) | Datacenter → Permissions → API Tokens |
| TrueNAS | API Key | UI → Credentials → API Keys |
| AdGuard Home | usuario/contraseña de la web UI | — |

## API REST (extracto)

| Endpoint | Descripción |
|---|---|
| `POST /api/scans` | Lanza un escaneo (`{"full": true}`) |
| `GET /api/scans/latest` | Último resultado completo |
| `GET /api/scans/progress` · `WS /ws/progress` | Progreso en vivo |
| `GET /api/devices` · `PATCH /api/devices/{mac}` | Inventario y trust |
| `GET /api/alerts` · `POST /api/alerts/{id}/ack` | Alertas |
| `GET /api/integrations/proxmox|truenas|adguard` | Salud de integraciones |
| `GET /api/overview` · `GET /api/capabilities` | Resumen y toolchain |

Docs interactivas en `http://localhost:8600/docs` (OpenAPI).

## Desarrollo

```bash
cd backend
pytest                    # suite completa
ruff check .              # lint
ruff format --check .     # formato
mypy src/netscan          # tipos

cd ../frontend
npm run lint && npm run typecheck && npm run build
```

CI en `.github/workflows/ci.yml`: matriz Ubuntu/Windows × Python 3.11/3.12,
lint+build del frontend, chequeo de licencias de dependencias y releases
automáticos al pushear tags `v*`.

## Estructura

```
├── backend/src/netscan/
│   ├── scanner/        # discovery (ARP), enrich, mDNS, fingerprint, tools, engine
│   ├── db/             # SQLModel: inventario, escaneos, alertas
│   ├── integrations/   # proxmox · truenas · adguard
│   ├── api/            # FastAPI + WebSocket + scheduler
│   ├── alerts/         # Apprise
│   ├── config.py       # YAML + env (pydantic-settings)
│   └── cli.py          # typer: scan · caps · serve
├── frontend/src/
│   ├── sections/       # Header, StatCards, DevicesTable, Integrations, AlertsFeed…
│   ├── hooks/          # polling + WebSocket
│   └── lib/api.ts      # cliente REST/WS
├── docker/             # Dockerfile.backend
├── legacy/             # netscan.py original (referencia histórica)
└── .github/workflows/  # CI + release + dependabot
```

## Licencias

NetScan se distribuye bajo **GPL-2.0-or-later** (requerido por scapy,
GPL-2.0-only). Las dependencias importadas son compatibles (MIT/BSD/Apache/
LGPL). Las herramientas GPL/AGPL/NPSL (nmap, RustScan, masscan, nuclei,
whatweb, testssl.sh) **no se distribuyen**: se invocan como procesos externos
cuando están instaladas ("mere aggregation"), y cada función degrada con
elegancia si la herramienta no está presente. Atribución completa en
[NOTICE](NOTICE).

## Contribuir

Ver [CONTRIBUTING.md](docs/CONTRIBUTING.md). Issues y PRs bienvenidos.

---

*English summary: NetScan is a GPL-2.0 homelab network scanner + live
inventory + monitoring dashboard (React/FastAPI) with Proxmox VE, TrueNAS and
AdGuard Home integrations, new-device intrusion alerts, mDNS IoT discovery,
TLS fingerprinting and optional nmap/RustScan/nuclei superpowers. Clone it,
`pip install -e backend`, `netscan serve`, and open the dashboard.*
