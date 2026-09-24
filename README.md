# NetScan — Homelab Network & Systems Monitor

[![CI](https://github.com/abarriuso/netscan/actions/workflows/ci.yml/badge.svg)](https://github.com/abarriuso/netscan/actions/workflows/ci.yml)
[![License: GPL v2+](https://img.shields.io/badge/license-GPL--2.0--or--later-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

**English** · [Español](README.es.md)

Network scanner, live inventory and monitoring dashboard for homelabs, with
integrations you configure from the web itself for **Proxmox VE**,
**TrueNAS**, **AdGuard Home**, **Pi-hole** and any service of your own
(a bookmark with a custom logo).

> From one-off scans to a permanent watch: discover your network, spot
> intruders, keep an eye on your hypervisors and your NAS — all in one dashboard.

> [!WARNING]
> **Work in progress.** NetScan is under active development: the API, the
> database schema and the configuration may change between versions without
> backwards compatibility. Use it on your local network and do not expose the
> dashboard to the Internet.

## Screenshots

The dashboard (`http://localhost:8600`) has six views:

- **Live** — real-time network latency and a map of devices (online/offline).
- **Overview** — KPIs, system status, device inventory and alerts.
- **Devices** — detailed inventory with latency, jitter, loss, quality, open
  ports and trust; sortable columns and IP/MAC copied with one click.
- **Analytics** — latency/quality/throughput series, top vendors/OS/ports, web
  services and TLS findings.
- **Integrations** — Proxmox/TrueNAS/AdGuard/Pi-hole and custom bookmarks,
  configured from the web.
- **System** — host resources (CPU, memory, disks, network) and NetScan server
  status.

`netscan.sh doctor` / `netscan.bat doctor` — a diagnosis at a glance before starting:

<p align="center">
  <img src="docs/screenshots/doctor-cli.png" width="760" alt="netscan doctor: diagnostic table in the terminal">
</p>

```
┌────────────────────────────────────────────────────────────────┐
│  backend/   Python 3.11+ · FastAPI · SQLite · scapy            │
│  frontend/  React 19 · TypeScript · Vite · Tailwind · shadcn   │
│  CI/CD      GitHub Actions (lint · mypy · pytest · build)      │
│  Licence    GPL-2.0-or-later                                   │
└────────────────────────────────────────────────────────────────┘
```

## One-command install

**Windows:**

```bat
install.bat --run
```

**Linux / macOS / WSL:**

```bash
chmod +x install.sh netscan.sh && ./install.sh --run
```

Each one does EVERYTHING: checks for (and installs) Python and Node if missing,
creates the virtual environment, installs the backend and the external tools it
can (`nmap`, `RustScan`, `nuclei`…), builds the dashboard and starts it —
`http://localhost:8600` opens by itself. There is no second manual step. Full
details and options (`--minimal`, `--system`, Windows installer, Docker, WSL
with all 6 tools) in [Quick start](#quick-start--a-single-command).

## What it does

**Discovery and fingerprinting**
- ARP scan (scapy) with vendor lookup by OUI
- mDNS/Bonjour (zeroconf) to name IoT devices that do not answer reverse DNS
- Multithreaded port scan + OS heuristics
- HTTP/TLS fingerprint of web UIs: title, `Server`, certificate issuer, expiry
  and self-signed certificates
- Optional external tools with **automatic detection and graceful
  degradation**: `nmap -sV` for real service versions, RustScan, nuclei,
  whatweb, testssl.sh (see [Licences](#licences))

**Live inventory (SQLite)**
- Every scan is compared with the stored inventory
- Alerts for a **new device** (home-made intrusion detection), IP↔MAC changes
  and devices going down
- Mark devices as "trusted" from the dashboard
- Notifications through Apprise: ntfy, Telegram, Discord and 80+ services

**Homelab integrations**
- **Proxmox VE** (several nodes/clusters): node, VM and CT status
- **TrueNAS** CORE/SCALE: pools, disks, SMART, system alerts
- **AdGuard Home** and **Pi-hole** (API v6): DNS queries, blocks, clients
  (cross-referenced with the network inventory)
- Custom bookmarks for any other service: name, URL and your own logo, with an
  up/down check
- Everything is added, edited and deleted **from the web itself** — no need to
  edit `netscan.yaml` by hand (instances defined there keep working, read-only
  in the panel)

**Speed test and quality metrics**
- Per-device speed test: mean/min/max **latency**, **jitter**, **packet loss**,
  **TCP handshake time per port** and, optionally, **real throughput (Mbps)**
  over HTTP
- A **0–100 quality score** per device and sample history
- On-demand speed test button on every row of the dashboard

**System status**
- Panel with the status of the **server (backend)** and the **frontend**:
  uptime, requests served, scans, WebSocket clients, auth, scheduler
- Host metrics through `psutil`: CPU (per core), RAM/swap, disks, and **live
  traffic per interface** (↓/↑), with the adapter's **link speed**
- **Animated** gauges and counters (no flicker; respects `prefers-reduced-motion`)

**Dashboard**
- Dense device table with ports, latency/jitter/loss/quality, version tooltips
  and filtering
- **Sortable columns** (host/IP/latency/jitter/loss/quality; values with no data
  always go last) and, on mobile, stacked cards that keep every metric instead
  of hiding columns
- Terminal-style **micro-interactions**: IP/MAC copied on click with a
  confirmation, tactile buttons, a tick on the active column and staggered row
  entry — all respecting `prefers-reduced-motion`
- Proxmox/TrueNAS/AdGuard/Pi-hole panels with pool and guest health, plus an
  integrations manager (add/edit/delete) and custom bookmarks
- Live scan progress over WebSocket, with a visible notice if it falls back to
  HTTP polling
- Alert feed with acknowledge
- Toasts with the API's real message on every action (trust, speed test,
  Wake-on-LAN, copy)

## Quick start — a single command

After installing, **`netscan up`** starts the API **and** the built-in
dashboard in a single process and port (`http://localhost:8600`) and opens the
browser.

**Windows:**

```bat
install.bat --run
```

It installs Python/Node (through winget if missing), creates the venv, installs
the backend and the external tools (nmap, RustScan, nuclei, Npcap), **builds
the dashboard** and, with `--run`, launches it. After that you only need:

```bat
netscan.bat up            REM  API + dashboard + browser (self-elevating)
```

`install.bat --minimal` skips the external tools. With no arguments,
`netscan.bat` already runs `up`.

**Linux / macOS:**

```bash
chmod +x install.sh netscan.sh
./install.sh --run        # install everything and launch (or just ./install.sh)
./netscan.sh up           # API + dashboard + browser (elevates itself with sudo)
```

`./install.sh` detects apt/dnf/pacman/brew for the system dependencies and
degrades gracefully for whatever it cannot install.

**Windows installer (a regular program):**

```bat
winget install JRSoftware.InnoSetup
iscc packaging\windows\netscan.iss        REM  -> packaging\windows\Output\NetScan-Setup.exe
```

`NetScan-Setup.exe` shows up in "Add or remove programs", creates Start menu
shortcuts and leaves everything ready. In CI it is built by `installer.yml`
(`workflow_dispatch`, or reused by `release.yml`), which also builds the Linux
package (`.tar.gz` with the backend + `frontend/dist` + `install.sh`) and
attaches both, together with the Python package, to every release of a `v*`
tag.

> **A tool does not show up as available in `netscan doctor` / `netscan caps`
> right after installing it?** On Windows, writing the user PATH does not update
> windows that are already open or existing shortcuts — close and reopen the
> terminal (or the dashboard) before reporting it as a bug. `install.bat`
> already does this for you in the same run; it only affects a
> `netscan.bat`/console opened *before* installing.

### Windows with all 6 tools

NetScan can use **6 external tools**: `nmap`, `RustScan`, `nuclei`, `whatweb`,
`testssl.sh` and `masscan` (the last one is detected but not used yet). They are
**really wired into the scan engine** — not just an indicator: each one does
something real when you launch it from the dashboard's "actions" menu or with
`netscan scan --full`.

The catch is that **`install.bat` (native Windows) can only install 3 of the
6**: `nmap`, `RustScan` and `nuclei` can be installed on Windows (winget, or a
SHA256-verified download). `whatweb` and `testssl.sh` **cannot** — they are
Linux tools (a Ruby gem, a bash script on top of OpenSSL) with no native Windows
equivalent. And `masscan`, although it compiles on Windows, has no maintained
winget package, so it is not installed either.

**The solution:** run NetScan inside **WSL** (Linux inside Windows) instead of
the native Windows NetScan. There all 6 can be installed. It takes two separate
steps — first WSL, then NetScan inside it:

**1. Install WSL (once, if you do not have it yet):**

Open PowerShell **as administrator** (right click → "Run as administrator") and
type:

```powershell
wsl --install
```

This installs Ubuntu by default. If it asks you to restart the PC, do so. After
restarting (or if it was not needed), look for **"Ubuntu"** in the Start menu
and open it — the first time it asks you to create a Linux user and password
(anything you like; it does not have to match your Windows account). That is
your Linux terminal, built into Windows.

**2. In that Ubuntu window, install the tools:**

Copy and paste this (one line, then Enter; it asks for the password you just
created):

```bash
sudo apt update && sudo apt install -y whatweb testssl.sh nmap masscan
```

If `testssl.sh` is not available in your Ubuntu version (some versions do not
package it), install it this way instead:

```bash
git clone --depth 1 https://github.com/drwetter/testssl.sh.git ~/testssl.sh
sudo ln -s ~/testssl.sh/testssl.sh /usr/local/bin/testssl.sh
```

**3. Start NetScan from inside WSL** (not with `netscan.bat` — that one is only
for the native Windows NetScan). Your `C:\` drive is visible from WSL under
`/mnt/c/`, so you go into the same repository you already have:

```bash
cd /mnt/c/path/to/netscan
./install.sh
./netscan.sh up
```

`./install.sh` installs RustScan and nuclei just like `install.bat` does on
Windows (and detects that `whatweb`/`testssl.sh` are already there from step 2),
and creates its own virtual environment in `backend/.venv-linux` — **separate**
from the `backend/.venv` used by Windows, even though it is the same checkout
seen from `/mnt/c/`. A Windows venv (`Scripts/python.exe`) and a Linux one
(`bin/python`) cannot share a folder without corrupting each other, so each
gets its own. `./netscan.sh up` starts the API + the dashboard. The browser opens
by itself; if not, go to `http://localhost:8600` — WSL2 shares the network with
Windows, so it works as if NetScan ran natively.

If `python3 -m venv` fails with `ensurepip is not available` (Ubuntu ships the
`venv` module as a separate package), `install.sh` detects it, installs the
missing package (`python3.XX-venv`) and retries — nothing to do by hand.

**4. Check that you see them all:**

```bash
./netscan.sh doctor
```

You should see all 6 in green (or "OK") except `masscan`, which shows as
detected but is not used by the engine yet (see the table below).

> **Important:** these are two *separate* NetScans — the native Windows one
> (`netscan.bat`, with 3 tools) and the WSL one (`netscan.sh`, with all 6). You
> do not need to uninstall the Windows one; use whichever you need. If you want
> WSL to start on its own when the PC boots, you can create a Windows scheduled
> task that runs `wsl ./netscan.sh up --no-browser`, but that is optional.

| Tool | Native Windows (`install.bat`) | WSL (`install.sh`) | Used by the engine? |
|---|---|---|---|
| nmap | ✅ | ✅ | Yes |
| RustScan | ✅ | ✅ | Yes |
| nuclei | ✅ | ✅ | Yes |
| whatweb | ❌ | ✅ | Yes |
| testssl.sh | ❌ | ✅ | Yes |
| masscan | ❌ | ✅ (via apt) | No — detected, not wired into the engine yet |

### Web service on Linux (systemd)

To run NetScan as a **web service** reachable on the LAN:

```bash
./install.sh --system
```

This creates `/etc/netscan/netscan.env` (bound to `0.0.0.0:8600` + a
**generated API token**), installs the `netscan.service` unit with the network
capabilities it needs (`CAP_NET_RAW`) and starts it. The dashboard is at
`http://<server-ip>:8600/`.

```bash
systemctl status netscan        # service status
journalctl -u netscan -f        # live logs
cat /etc/netscan/netscan.env    # get the token back if you no longer have it
```

The first time the dashboard makes a request without a valid token, a dialog
asking for it opens by itself (it is then saved in the browser); you can also
open it any time with the key icon 🔑 in the header, for example to change it
after rotating the token.

Manually (without systemd), as a foreground service:

```bash
NETSCAN_API_HOST=0.0.0.0 NETSCAN_API_TOKEN=my-token \
  ./netscan.sh up --no-browser --port 8600
```

Other useful commands: `netscan speedtest` (network speed test),
`netscan doctor` (full diagnosis), `netscan scan --full`.

### Proxmox LXC (one command from the host)

To run NetScan in its own container, visible from the whole LAN, from the
**Proxmox host shell** (not inside a container):

```bash
curl -fsSLO https://raw.githubusercontent.com/abarriuso/netscan/main/packaging/proxmox/create-lxc.sh
curl -fsSLO https://raw.githubusercontent.com/abarriuso/netscan/main/packaging/proxmox/bootstrap-lxc.sh
chmod +x create-lxc.sh
./create-lxc.sh
```

(`bootstrap-lxc.sh` has to sit next to `create-lxc.sh` — the latter copies it
into the new container automatically; you do not run it yourself.) If you would
rather not leave even those two files on the host, there is a one-liner that
downloads nothing permanent — when it does not find `bootstrap-lxc.sh` next to
itself, it fetches it into a temporary file in `/tmp`:

```bash
VMID=201 OS_TEMPLATE=ubuntu-26.04-standard bash -c "$(curl -fsSL https://raw.githubusercontent.com/abarriuso/netscan/main/packaging/proxmox/create-lxc.sh)"
```

And if you downloaded the two files and want to clean up afterwards, however
you ran it:

```bash
rm -f create-lxc.sh bootstrap-lxc.sh
```

When you run it by hand in a terminal, it asks for the VMID, name, template,
bridge and IP one by one (Enter accepts the proposed default). Anything already
set through an environment variable is not asked; and with no real terminal
involved (run from a pipe or something automated) it asks nothing at all and
uses the defaults, so it never hangs. It creates an unprivileged CT (**Ubuntu
26.04 LTS** by default — any Debian/Ubuntu template works, see `OS_TEMPLATE`;
2 vCPU / **2 GB of RAM** — 1 GB falls short and `oom-kill` takes the service
down halfway through the install, especially while building the dashboard),
starts it, clones the repository inside and runs `install.sh --system` — at the
end it prints the dashboard URL and where the token is. Everything can also be
set through environment variables (`VMID`, `CT_NAME`, `BRIDGE`, `IP`, `CORES`,
`MEMORY_MB`, `OS_TEMPLATE`, ...); see the header comments of
`packaging/proxmox/create-lxc.sh` for the full list. For example, to use
Debian 12 instead of Ubuntu without being asked anything:

```bash
OS_TEMPLATE=debian-12-standard ./create-lxc.sh
```

The whole process is truly unattended: `install.sh`/`bootstrap-lxc.sh` silence
the interactive `needrestart` dialog that Debian/Ubuntu ship (without that, an
`apt-get install` halfway through hangs forever with no error, waiting for a key
that never arrives through `pct exec`), and they install Node.js 20+ themselves
if the container does not have it (a bare LXC template never does) so the
dashboard can be built.

**The only setting that really matters:** `BRIDGE` (default `vmbr0`) must be a
bridge connected to your physical LAN, not NAT or an isolated SDN zone — the ARP
scan only discovers what is on its own L2 segment. That is decided when the
container is created; it cannot be fixed from inside afterwards.

If you already have a Linux CT/VM (with a properly connected network) and only
want the install part, `bootstrap-lxc.sh` on its own is enough, run as root
inside the container:

```bash
curl -fsSL https://raw.githubusercontent.com/abarriuso/netscan/main/packaging/proxmox/bootstrap-lxc.sh | bash
```

### Docker (experimental)

```bash
cp netscan.example.yaml netscan.yaml
docker compose up --build
# API on :8600, dashboard on :8601
```

The backend uses host networking (`network_mode: host`) so that ARP discovery
sees your LAN, which needs a **Linux** Docker host. The dashboard container
reaches the API through `host.docker.internal`, while the backend listens on
`127.0.0.1` by default, so the dashboard on `:8601` cannot reach the API unless
the backend listens on the network (`NETSCAN_API_HOST=0.0.0.0` together with a
`NETSCAN_API_TOKEN`). On Docker Desktop (Windows/macOS) the dashboard gets a
`502`. For now, prefer the native install, WSL or the Proxmox LXC.

## Configuration

All configuration lives in `netscan.yaml` (see `netscan.example.yaml`) and can
be overridden with `NETSCAN_*` environment variables:

```bash
NETSCAN_PROXMOX__0__TOKEN_SECRET=xxxx   # token secret for pve1
NETSCAN_TRUENAS__0__API_KEY=xxxx
NETSCAN_NOTIFY_URLS__0=ntfy://ntfy.sh/my-topic
```

`netscan.yaml` and `config.local.yaml` are git-ignored, but secrets should still
**always** go in environment variables, never in the YAML file.

### Credentials you need

| Service | What to create | Where |
|---|---|---|
| Proxmox VE | API token (`PVEAPIToken`) | Datacenter → Permissions → API Tokens |
| TrueNAS | API key | UI → Credentials → API Keys |
| AdGuard Home | web UI user/password | — |
| Pi-hole | admin password | — (API v6) |

## REST API (excerpt)

| Endpoint | Description |
|---|---|
| `POST /api/scans` | Start a scan (`{"full": true}`) |
| `GET /api/scans/latest` | Latest full result |
| `GET /api/scans/progress` · `WS /ws/progress` | Live progress |
| `GET /api/devices` · `PATCH /api/devices/{mac}` | Inventory and trust |
| `GET /api/alerts` · `POST /api/alerts/{id}/ack` | Alerts |
| `GET /api/integrations/proxmox|truenas|adguard` | Integration health |
| `GET /api/overview` · `GET /api/capabilities` | Summary and toolchain |
| `GET /api/system` · `GET /api/status` | Server/host/frontend status (all in one) |
| `GET /api/metrics/summary` | Aggregated quality metrics |
| `GET /api/devices/{mac}/metrics` | Latency/jitter/quality history |
| `POST /api/devices/{mac}/speedtest` | On-demand speed test for a device |
| `POST /api/devices/{mac}/wake` | Wake-on-LAN |

With the dashboard built, the API **and** the web UI are served on the same port
(`/` = dashboard, `/api/...` = API). Interactive docs at
`http://localhost:8600/docs` (OpenAPI).

### Error messages

Every API error response arrives as JSON `{"detail": "..."}` with a readable
message (currently in Spanish), and the dashboard shows that text directly in a
toast — never a bare code. An unexpected server error is caught globally and
turned into a `500` with a readable `detail`; the technical detail (traceback)
stays in the NetScan log, not in the client.

| Code | Meaning | What to check |
|---|---|---|
| `400` | Malformed request (e.g. invalid network range) | Check the request body/parameters |
| `401` | Missing or wrong token | Set the token in the dashboard (key icon) or `NETSCAN_API_TOKEN` |
| `403` | Origin not allowed (CORS) | Add the origin to `NETSCAN_API_CORS_ORIGINS` |
| `404` | Resource does not exist (e.g. no scan yet) | Run a scan; check the MAC/path |
| `409` | Conflict (e.g. a scan is already running) | Wait for the running scan to finish |
| `413` | File too large (e.g. integration logo) | The logo cannot exceed 2 MB |
| `415` | Unsupported content type | Upload PNG/JPG/SVG for the logo |
| `422` | Field validation failed | The `detail` lists which field fails |
| `429` | Too many requests | Poll less often or wait |
| `500` | Unhandled internal error | Check the NetScan logs (see below) |

## Troubleshooting

- **The dashboard loads blank / no data appears.** Check that the API answers:
  `curl http://localhost:8600/api/health` must return `{"status":"ok"}`. If not,
  the service is not running (see systemd above).
- **`401` when opening the dashboard.** A token is set on the server but the
  browser does not have it. Press the key icon in the header and enter it; it is
  saved in the browser. The token is `NETSCAN_API_TOKEN`.
- **The port is already in use.** Change `NETSCAN_API_PORT` (and
  `NETSCAN_API_HOST` if you only want to listen on localhost). On Linux:
  `ss -tlnp | grep 8600` shows what is using it.
- **The ARP scan finds no devices.** Usually permissions or network. Layer-2
  scanning needs privileges (on Linux, `cap_net_raw` or root; the systemd
  service already grants it). In LXC, the container must be bridged onto the
  same VLAN you want to scan.
- **`403` / CORS errors from another machine.** Add the browser's origin (e.g.
  `http://192.168.1.50:8601`) to `NETSCAN_API_CORS_ORIGINS` (comma-separated
  list).
- **An integration (Proxmox/TrueNAS/AdGuard) shows red.** Check the URL,
  credentials and that the target is reachable from the NetScan host. The
  integration error's `detail` says what failed (DNS, TLS, auth…).
- **Where are the logs?** In `NETSCAN_DATA_DIR/netscan.log` (as well as standard
  output). With systemd: `journalctl -u netscan -f`.

## Development

```bash
cd backend
pytest                    # full suite
ruff check .              # lint
ruff format --check .     # formatting
mypy src/netscan          # types

cd ../frontend
pnpm lint && pnpm typecheck && pnpm build
```

CI in `.github/workflows/ci.yml`: Ubuntu/Windows × Python 3.11/3.12 matrix,
frontend lint+build, dependency licence check, vulnerability audit
(`pip-audit` + `pnpm audit`) and automatic releases when `v*` tags are pushed
(backend + Windows installer + Linux bundle, see `release.yml`).

## Layout

```
├── backend/src/netscan/
│   ├── scanner/        # discovery (ARP), enrich, mDNS, fingerprint, tools, speed, engine
│   ├── db/             # SQLModel: inventory, scans, alerts, metric samples
│   ├── integrations/   # proxmox · truenas · adguard
│   ├── api/            # FastAPI + WebSocket + scheduler + static dashboard
│   ├── alerts/         # Apprise
│   ├── system.py       # host/process/frontend status (psutil)
│   ├── config.py       # YAML + env (pydantic-settings)
│   └── cli.py          # typer: up · scan · speedtest · doctor · caps · serve · wake
├── frontend/src/
│   ├── sections/       # Header, StatCards, SystemStatus, DevicesTable, Integrations…
│   ├── components/     # metrics.tsx (animated number, gauge, quality badge)
│   ├── hooks/          # polling + WebSocket + animations
│   └── lib/api.ts      # REST/WS client
├── packaging/
│   ├── windows/        # netscan.iss (Inno Setup → NetScan-Setup.exe)
│   └── linux/          # netscan.service (systemd) · netscan.desktop
├── install.sh · netscan.sh   # Linux/macOS installer and launcher
├── install.bat · netscan.bat # Windows installer and launcher
├── docker/             # Dockerfile.backend
├── legacy/             # the original netscan.py (historical reference)
└── .github/workflows/  # CI + release + installer + dependabot
```

## Licences

NetScan is released under **GPL-2.0-or-later** (required by scapy,
GPL-2.0-only). The imported dependencies are compatible (MIT/BSD/Apache/LGPL).
The GPL/AGPL/NPSL tools (nmap, RustScan, masscan, nuclei, whatweb, testssl.sh)
**are not distributed**: they are invoked as external processes when installed
("mere aggregation"), and each feature degrades gracefully if the tool is
missing. Full attribution in [NOTICE](NOTICE).

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md). Issues and PRs welcome.
