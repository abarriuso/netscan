# Architecture

## Overview

```mermaid
flowchart LR
  subgraph clients[" "]
    UI["Dashboard<br/>React 19 · Vite · Tailwind"]
    CLI["CLI (typer)<br/>up · scan · doctor · speedtest"]
    PROM["Prometheus / Grafana"]
  end
  subgraph proc["netscan — one process, port 8600"]
    API["FastAPI<br/>REST · /ws/progress · /ws/events · /metrics"]
    BUS[["events.bus<br/>ring buffer · seq"]]
    SCHED["Scheduler<br/>periodic scans"]
    ENGINE["engine.run_scan()"]
    LIVE["LiveMonitor<br/>ICMP → TCP → ARP every 5 s"]
    STORE[("SQLite<br/>inventory · scans · alerts · metrics<br/>uptime buckets · device timeline")]
    INSIGHTS["insights · security · classify<br/>uptime · map · IPAM · risk"]
    DIAG["diag<br/>ping · traceroute · DNS · HTTP · TLS"]
    INTEG["integrations"]
    NOTIFY["Apprise"]
  end
  UI <-->|REST · WebSocket| API
  PROM -->|scrape| API
  CLI --> ENGINE
  API --> ENGINE & INSIGHTS & DIAG & INTEG
  SCHED --> ENGINE
  ENGINE -->|record_scan| STORE
  LIVE -->|state · buckets| STORE
  STORE --> INSIGHTS
  STORE -->|alerts| NOTIFY
  ENGINE & LIVE & DIAG & INTEG & API -.->|emit| BUS
  BUS -.->|/ws/events| UI
  ENGINE --> LAN(("LAN"))
  LIVE --> LAN
```

### Scan pipeline

```mermaid
flowchart TD
  A{"privileged?"} -->|yes| A1["ARP sweep (scapy)<br/>IP conflicts detected"]
  A -->|no| A2["ICMP sweep (native API, 64 threads)<br/>+ OS ARP cache"]
  A1 & A2 --> A3["+ the NetScan host itself (own MAC)"]
  A3 --> B["OUI vendors · mDNS — main thread"]
  B --> C["Per-device enrichment, thread pool"]
  C --> C1["ICMP echo · PTR lookup in background (1.5 s grace)"]
  C --> C2["open ports: RustScan full range,<br/>or threaded TCP connect (27 / 58 ports)"]
  C2 --> C3["nmap -sV versions (+ OS guess)"]
  C --> C4["HTTP/TLS fingerprint: legacy-TLS capable,<br/>first hop kept if a redirect fails"]
  C --> C5["speed test: 5 echoes, TCP fallback"]
  C1 & C3 & C4 & C5 --> D["full scan: nuclei · whatweb · testssl.sh (if installed)"]
  D --> E["record_scan: diff by MAC"]
  E --> F1["new_device"] & F2["mac_changed (IP moved)"] & F3["ports_changed"] & F4["ip_conflict"] & F5["gateway_mac_changed"] & F6["online/offline + timeline"]
  F1 & F2 & F3 & F4 & F5 --> G["Apprise notification"]
```

## Modules

| Module | Role |
|---|---|
| `events.py` | Process-wide event bus: bounded ring buffer (5000), monotonic `seq`, thread-safe fan-out to `/ws/events`, `info+` mirrored to `netscan.log`. `BusLogHandler` forwards warnings/errors from ordinary loggers. |
| `scanner/icmp.py` | ICMP echo without spawning processes: Windows `IcmpSendEcho`, POSIX datagram/raw sockets, `ping` as last resort; `arp_probe` (Windows `SendARP`). |
| `scanner/discovery.py` | Local network/gateway detection, ARP scan (scapy), unprivileged sweep (ICMP + neighbour table), neighbour-table parsers for Windows/Linux/BSD. |
| `scanner/engine.py` | Orchestration; resolves which stages run and why the others are skipped; emits one event per host/stage. |
| `scanner/enrich.py` · `speed.py` · `fingerprint.py` · `tools.py` · `mdns.py` | Ports, latency/jitter/loss/quality, HTTP/TLS, external tools (exact command lines on the event feed), mDNS. |
| `live.py` | Live monitor: probe chain, hysteresis state machine, 5-min uptime buckets, gateway/WAN RTT. |
| `db/store.py` | Inventory diff and persistence: devices, scans, alerts, metric samples, uptime buckets, device timeline, meta (gateway MAC). |
| `classify.py` | Role inference with reasons; MAC analysis (randomized, virtual NIC). |
| `security.py` | Risk score with itemized factors (evidence + remediation). |
| `insights.py` | Uptime report (windows, coverage, slots, outages, MTTR), network map, IP map, security report, Prometheus exposition. |
| `diag.py` | Toolbox: ping, native traceroute, RFC 1035 DNS client + resolver benchmark, TCP check, HTTP phase timing, TLS inspection, subnet and MAC calculators. |
| `api/app.py` + `routes_events.py` · `routes_insights.py` · `routes_toolbox.py` | REST/WebSocket surface. |

Frontend: `lib/eventStream.ts` (shared `/ws/events` connection with replay and
HTTP-polling fallback), `lib/telemetry.ts` (browser-side events: every API
call with status, time and size, WebSocket state, uncaught errors),
`lib/format.ts` (the single place where units are formatted), `sections/*`
(one per tab, all lazy-loaded except the shell).

## Key decisions

- **A single `engine.run_scan()`** serves the CLI and the API. Coarse progress
  goes through a `(stage, done, total)` callback (CLI progress bar, header
  progress); fine-grained detail goes to the event bus.
- **Transparency by default.** Every probe, command line, HTTP request,
  certificate, state change and API call produces an event. A stage that does
  not run says why (`skipped — nmap -sV: not installed`). Scan failures carry
  the real exception message to the dashboard instead of "see the log".
- **Degrade, don't fail.** Without admin rights the ARP scan is replaced by an
  ICMP sweep plus the OS neighbour cache — the ping attempt makes the OS ARP
  the host, so ICMP-filtering PCs still appear. Missing tools are skipped and
  reported.
- **No subprocess per probe.** The previous `ping.exe` per echo cost
  30–80 ms of process start-up on Windows (more than a LAN RTT), and its exit
  code 0 on "Destination host unreachable" counted dead hosts as alive.
- **Hysteresis for state.** Down after N failed probes, up on the first
  answer; transitions are stored once, so scans and the live monitor never
  double-alert.
- **Honest availability.** Uptime is computed only over observed time and
  always shown with its coverage; a gap is "no data", never "down".
- **Inventory diff by MAC.** The MAC is the stable key. Ports are diffed only
  within the probed set, so a quick scan after a full one does not "close"
  the extended ports; a host that answered nothing is not diffed.
- **Explained scores.** Role, quality and risk always come with the reasons
  or formula behind them (see [METRICS.md](METRICS.md)).
- **Optional external tools.** `scanner/tools.py` detects binaries with
  `shutil.which`; nothing fails because nmap is not installed.
- **Fault-tolerant integrations.** `collect_all()` isolates each instance's
  failure; HTTP clients are closed after each poll and Pi-hole sessions are
  reused (v6 caps concurrent sessions).
- **Secrets outside the repository.** pydantic-settings merges YAML + env;
  tokens live in `NETSCAN_*` variables.

## Planned extensions

- SNMP polling (interface counters, LLDP/CDP neighbours) for a real L2 topology.
- Wiring `masscan` into the engine (today it is detected but not used).
