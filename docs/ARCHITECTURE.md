# Architecture

## Overview

```mermaid
flowchart LR
  subgraph clients[" "]
    UI["Dashboard<br/>React 19 · Vite · Tailwind"]
    CLI["CLI (typer)<br/>up · scan · doctor · speedtest"]
  end
  subgraph proc["netscan — one process, port 8600"]
    API["FastAPI<br/>REST + WebSocket /ws/progress"]
    SCHED["Scheduler<br/>periodic scans"]
    ENGINE["engine.run_scan()"]
    STORE[("SQLite<br/>inventory · scans · alerts · metrics")]
    LIVE["LiveMonitor<br/>pings known devices"]
    INTEG["integrations.collect_all()"]
    SYS["system.py<br/>host metrics (psutil)"]
    NOTIFY["Apprise<br/>ntfy · Telegram · Discord…"]
  end
  UI <-->|REST / WebSocket| API
  CLI --> ENGINE
  API --> ENGINE
  SCHED --> ENGINE
  ENGINE -->|record_scan: diff by MAC| STORE
  STORE -->|new alerts| NOTIFY
  API --> STORE & LIVE & INTEG & SYS
  ENGINE --> LAN(("LAN"))
  LIVE --> LAN
  INTEG --> PVE["Proxmox VE"] & TN["TrueNAS"] & AG["AdGuard Home"] & PH["Pi-hole"]
```

### Scan pipeline

```mermaid
flowchart TD
  A["ARP sweep (scapy)<br/>every host on the L2 segment"] --> B["OUI vendors + mDNS names<br/>main thread: not thread-safe"]
  B --> C["Per-device enrichment, thread pool"]
  C --> C1["reverse DNS · ping"]
  C --> C2["open ports: RustScan full range,<br/>or the built-in threaded scan"]
  C2 --> C3["nmap -sV versions (+ OS guess)"]
  C --> C4["HTTP/TLS fingerprint:<br/>title, server, certificate"]
  C --> C5["speed test: latency, jitter,<br/>loss, throughput (optional)"]
  C1 & C3 & C4 & C5 --> D["web UIs found → nuclei · whatweb · testssl.sh<br/>(only if installed; nuclei capped)"]
  D --> E["record_scan: diff with the inventory, keyed by MAC"]
  E -->|unknown MAC| F1["new_device"]
  E -->|IP ↔ MAC change| F2["mac_changed"]
  E -->|host missing| F3["device_down"]
  F1 & F2 & F3 --> G["Apprise notification"]
```

## Key decisions

- **A single `engine.run_scan()`** serves both the CLI and the API. Progress is
  reported through a `(stage, done, total)` callback that the CLI draws with
  rich and the API forwards over WebSocket.
- **Non-thread-safe steps on the main thread**: the OUI lookup
  (mac_vendor_lookup) and mDNS are resolved before the thread pool; per-device
  enrichment runs concurrently.
- **Inventory diff by MAC**: the MAC is the stable key; an IP change raises a
  `mac_changed` alert and an unknown MAC a `new_device` one.
- **Optional external tools**: `scanner/tools.py` detects binaries with
  `shutil.which`, exposes `Capabilities` to the API (`/api/capabilities`) and
  each wrapper returns `None`/empty when the tool is missing. Nothing fails
  because nmap is not installed.
- **Fault-tolerant integrations**: `collect_all()` catches any exception per
  instance and returns it as `{"error": ...}` — a Proxmox host that is down does
  not bring the dashboard down.
- **Secrets outside the repository**: pydantic-settings merges YAML + env;
  tokens live in `NETSCAN_*` variables.

## Planned extensions

- SNMP (port 161) through a direct query or nmap NSE scripts.
- Wiring `masscan` into the engine (today it is detected but not used).
