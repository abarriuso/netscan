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

**Speed test y métricas de calidad (nuevo)**
- Test de velocidad por dispositivo: **latencia** media/mín/máx, **jitter**,
  **pérdida de paquetes**, **tiempo de handshake TCP por puerto** y, opcional,
  **throughput real (Mbps)** por HTTP
- Puntuación de **calidad 0–100** por dispositivo e histórico de muestras
- Botón de speed test bajo demanda en cada fila del dashboard

**Estado del sistema (nuevo)**
- Panel con el estado del **terminal server (backend)** y del **frontend**:
  uptime, peticiones servidas, escaneos, clientes WebSocket, auth, scheduler
- Métricas del host vía `psutil`: CPU (por núcleo), RAM/swap, discos, y
  **tráfico en vivo por interfaz** (↓/↑), con **link speed** del adaptador
- Medidores y contadores **animados** (sin parpadeos; respeta `prefers-reduced-motion`)

**Dashboard**
- Tabla densa de dispositivos con puertos, latencia/jitter/pérdida/calidad,
  tooltips de versión y filtrado
- Paneles de Proxmox/TrueNAS/AdGuard con salud de pools y guests
- Progreso de escaneo en vivo por WebSocket
- Feed de alertas con acknowledge

## Arranque rápido — un solo comando

Tras instalar, **`netscan up`** arranca la API **y** el dashboard integrado en
un único proceso y puerto (`http://localhost:8600`) y abre el navegador.

**Windows:**

```bat
install.bat --run
```

Instala Python/Node (vía winget si faltan), crea el venv, instala el backend,
las herramientas externas (nmap, RustScan, nuclei, Npcap), **compila el
dashboard** y con `--run` lo lanza. Luego basta con:

```bat
netscan.bat up            REM  API + dashboard + navegador (auto-elevado)
```

`install.bat --minimal` omite las herramientas externas. Sin argumentos,
`netscan.bat` ya ejecuta `up`.

**Linux / macOS:**

```bash
chmod +x install.sh netscan.sh
./install.sh --run        # instala todo y lanza (o ./install.sh a secas)
./netscan.sh up           # API + dashboard + navegador (se auto-eleva con sudo)
```

`./install.sh` detecta apt/dnf/pacman/brew para las dependencias del sistema y
degrada con elegancia lo que no pueda instalar.

**Instalador de Windows (programa normal):**

```bat
winget install JRSoftware.InnoSetup
iscc packaging\windows\netscan.iss        REM  -> packaging\windows\Output\NetScan-Setup.exe
```

`NetScan-Setup.exe` aparece en "Agregar o quitar programas", crea accesos en
el menú Inicio y deja todo listo. En CI lo compila `installer.yml`
(`workflow_dispatch` o reutilizado por `release.yml`), que también genera el
paquete Linux (`.tar.gz` con backend + `frontend/dist` + `install.sh`) y
adjunta ambos, junto al paquete Python, a cada release de un tag `v*`.

> **¿Una herramienta no aparece como disponible en `netscan doctor` /
> `netscan caps` justo después de instalarla?** En Windows, escribir el PATH
> de usuario no actualiza por sí solo las ventanas ya abiertas ni los accesos
> directos existentes — cierra y reabre la terminal (o el dashboard) antes de
> reportarlo como bug. `install.bat` ya lo hace por ti en la misma ejecución;
> solo afecta a una `netscan.bat`/consola abierta *antes* de instalar.

### Servicio web en Linux (systemd)

Para dejar NetScan como **servicio web** accesible en la LAN:

```bash
./install.sh --system
```

Esto crea `/etc/netscan/netscan.env` (bind a `0.0.0.0:8600` + **token de API
generado**), instala la unidad `netscan.service` con las capacidades de red
necesarias (`CAP_NET_RAW`) y la arranca. El dashboard queda en
`http://<ip-del-servidor>:8600/`.

```bash
systemctl status netscan        # estado del servicio
journalctl -u netscan -f        # logs en vivo
```

Manual (sin systemd), como servicio en primer plano:

```bash
NETSCAN_API_HOST=0.0.0.0 NETSCAN_API_TOKEN=mi-token \
  ./netscan.sh up --no-browser --port 8600
```

Otros comandos útiles: `netscan speedtest` (test de velocidad de la red),
`netscan doctor` (diagnóstico completo), `netscan scan --full`.

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
| `GET /api/system` · `GET /api/status` | Estado del server/host/frontend (todo en uno) |
| `GET /api/metrics/summary` | Métricas de calidad agregadas |
| `GET /api/devices/{mac}/metrics` | Histórico de latencia/jitter/calidad |
| `POST /api/devices/{mac}/speedtest` | Speed test bajo demanda de un dispositivo |
| `POST /api/devices/{mac}/wake` | Wake-on-LAN |

Con el dashboard compilado, la API **y** la web se sirven en el mismo puerto
(`/` = dashboard, `/api/...` = API). Docs interactivas en
`http://localhost:8600/docs` (OpenAPI).

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
lint+build del frontend, chequeo de licencias de dependencias, auditoría de
vulnerabilidades (`pip-audit` + `npm audit`) y releases automáticos al
pushear tags `v*` (backend + instalador Windows + bundle Linux, ver
`release.yml`).

## Estructura

```
├── backend/src/netscan/
│   ├── scanner/        # discovery (ARP), enrich, mDNS, fingerprint, tools, speed, engine
│   ├── db/             # SQLModel: inventario, escaneos, alertas, muestras de métricas
│   ├── integrations/   # proxmox · truenas · adguard
│   ├── api/            # FastAPI + WebSocket + scheduler + estático del dashboard
│   ├── alerts/         # Apprise
│   ├── system.py       # estado del host/proceso/frontend (psutil)
│   ├── config.py       # YAML + env (pydantic-settings)
│   └── cli.py          # typer: up · scan · speedtest · doctor · caps · serve · wake
├── frontend/src/
│   ├── sections/       # Header, StatCards, SystemStatus, DevicesTable, Integrations…
│   ├── components/     # metrics.tsx (número animado, medidor, badge de calidad)
│   ├── hooks/          # polling + WebSocket + animaciones
│   └── lib/api.ts      # cliente REST/WS
├── packaging/
│   ├── windows/        # netscan.iss (Inno Setup → NetScan-Setup.exe)
│   └── linux/          # netscan.service (systemd) · netscan.desktop
├── install.sh · netscan.sh   # instalador y lanzador Linux/macOS
├── install.bat · netscan.bat # instalador y lanzador Windows
├── docker/             # Dockerfile.backend
├── legacy/             # netscan.py original (referencia histórica)
└── .github/workflows/  # CI + release + installer + dependabot
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
