# Metrics, units and definitions

Every number NetScan shows, what it measures, how, and in which unit. If a
value cannot be measured it is shown as **—** (never as `0`).

## Unit conventions

| Quantity | Unit | Notes |
|---|---|---|
| Time / latency | **ms** (milliseconds), float | Precision follows the magnitude: `0.41 ms`, `3.7 ms`, `125 ms`. LAN RTTs are sub-millisecond, so integer ms would hide them. |
| Durations | s · min · h · d | Two most significant units: `3 min 12 s`, `2 d 4 h`. |
| Data sizes | **IEC binary**: B, KiB, MiB, GiB (powers of **1024**) | `fmtBytes`. Memory, disks, response bodies. |
| Data rates | **bit/s with SI prefixes**: kbit/s, Mbit/s, Gbit/s (powers of **1000**) | `fmtBitRate`. Throughput and link speed. 1 Mbit/s = 10⁶ bit/s. |
| Ratios | **%** with explicit decimals | Availability gets more decimals near 100 % (`99.95 %`), where they matter. |
| Scores | 0–100 integer | Quality (higher = better), risk (higher = worse). |
| Timestamps | ISO 8601, server local time | Shown in the browser's locale, with the date when it is not today. |

API field names carry their unit (`*_ms`, `*_s`, `*_pct`, `*_mbps`,
`*_bytes`, `*_bytes_per_s`). Prometheus metrics follow Prometheus
conventions instead: **seconds** and **ratios 0–1** (`netscan_device_rtt_seconds`,
`netscan_device_availability_ratio`).

Legacy names kept for compatibility: `network.interfaces[].up_bps`/`down_bps`
are **bytes** per second (use `tx_bytes_per_s`/`rx_bytes_per_s`);
`memory.free` is truly free RAM (use `available_bytes` for "allocatable
without swapping").

## Round-trip time (RTT)

| Source | How | Resolution |
|---|---|---|
| ICMP, Windows | `IcmpSendEcho` (iphlpapi.dll), no admin, no `ping.exe` | Wall clock of the call (µs timer), clamped to ±1 ms of the kernel's integer RTT |
| ICMP, Linux/macOS | unprivileged `SOCK_DGRAM` ICMP socket (or `SOCK_RAW` as root) | µs |
| ICMP fallback | system `ping` | as printed; `time<1ms` → 0.5 ms (midpoint), replies must contain `ttl=` |
| TCP handshake | `connect()` SYN → SYN/ACK | µs; one RTT plus the kernel's accept, used when ICMP is filtered |

`rtt_source` says which one produced a figure: `icmp`, `tcp/<port>` or `""`
(nothing answered → not measurable).

## Per-device quality metrics (scan / on-demand speed test)

5 ICMP echoes per device (`scan.speedtest_pings`), timeout `scan.ping_timeout`.

- **latency avg / min / max** — over the echoes that answered (ms).
- **jitter** — mean absolute difference between consecutive RTTs (RFC 3550
  style), ms. 0 with a single sample.
- **packet loss** — echoes lost / echoes sent × 100. If ICMP is filtered but a
  TCP port answers, RTT, jitter and loss are measured over 5 TCP handshakes to
  that port instead (loss = failed handshakes). If nothing answers, loss and
  quality are **—**.
- **TCP handshake** — connect time to every known open port; the mean is
  shown (ms).
- **throughput** (opt-in, `use_throughput`) — HTTP GET of up to 4 MiB from a
  web port. The clock starts at the **first body byte** (TCP/TLS set-up and
  server think time are latency, not bandwidth); responses under 256 KiB are
  rejected as too small to measure. Mbit/s (10⁶ bit/s).
- **quality (0–100)** = `100 − loss% − min(1.2 × (latency − 1 ms), 40) − min(2 × jitter, 20)`,
  clamped to 0–100. 100 % loss → 0; unmeasurable → —.

Network-wide: **average latency** = mean of the online devices' last RTT;
**p95** = 95th percentile of the same set; **worst quality** = minimum.
The trend charts average one point per scan (on-demand speed tests are
excluded so a single device never becomes a "network average").

## Live monitor, uptime and outages

Every `scan.live_interval_s` (default 5 s) each known device is probed, cheapest
first, stopping at the first answer:

1. ICMP echo
2. TCP `connect()` to up to 3 known open ports
3. ARP who-has (Windows `SendARP`, unprivileged — catches hosts that drop
   everything else). Proves L2 presence; no RTT is reported for it.

- **State with hysteresis** — a device becomes **down** after
  `scan.live_down_after` (default 3) consecutive failed probes, **up** again on
  the first answer. Transitions go to the device timeline and, if
  `alert_on_device_down`, to alerts.
- **"up for ≥ X"** — the `≥` means the state started before NetScan began
  watching that device (after a restart), so X is a lower bound.
- **Uptime buckets** — probe counters aggregated per device per 5 min
  (`probes`, `up`, RTT sum/count/min/max), kept 35 days.
- **Availability %** = probes answered / probes sent in the window
  (1 h, 24 h, 7 d, 30 d) — only over the time NetScan was running.
- **Coverage %** = probes sent / probes that would have been sent if NetScan
  had run the whole window. "100 % availability at 3 % coverage" means "never
  seen down in the 3 % of the window that was observed".
- **Timeline bars** — one bar per slot (window / N): green ≥ 99.5 %, lime
  ≥ 95 %, amber ≥ 80 %, red < 80 %, **grey = no data** (never counted as down).
- **Outage** — a confirmed down transition until the next up transition.
  **MTTR** = mean duration of the closed outages in the last 30 days.
- **Gateway RTT / Internet RTT** — the default gateway and the
  `scan.live_wan_targets` (default 1.1.1.1, 8.8.8.8) are pinged every tick;
  **Internet loss** = targets that did not answer, averaged over the last
  minute. Comparing LAN vs gateway vs WAN tells "my LAN" from "my ISP".

## Risk score (0–100)

Additive, capped at 100. Levels: **0–19 low · 20–44 medium · 45–69 high ·
70–100 critical**. Every point comes from a named factor with its evidence and
remediation (`/api/security`, device profile → risk).

| Factor | Points |
|---|---|
| Not marked as trusted | 15 |
| First seen < 24 h ago | 10 |
| Docker API 2375 | 40 |
| Telnet 23 | 30 |
| Redis 6379, MongoDB 27017 | 25 |
| Elasticsearch 9200, VNC 5900 | 20 |
| FTP 21, RDP 3389, MQTT 1883 | 15 |
| SMB 445, WinRM 5985, MySQL 3306, PostgreSQL 5432, MSSQL 1433, Oracle 1521 | 10 |
| NetBIOS 139, rpcbind 111 | 5 |
| > 10 open TCP ports | 10 |
| Expired certificate / expires < 14 d | 20 / 10 |
| TLS 1.0/1.1/SSL negotiated | 15 |
| Self-signed certificate | 3 |
| Login page over plain HTTP | 8 |
| nuclei / testssl.sh finding: critical / high / medium / low | 40 / 25 / 10 / 3 |
| IP conflict (two MACs answered ARP for the IP) | 30 |
| Randomized MAC and not trusted | 5 |

The model is a LAN (homelab) exposure model, not Internet-facing CVSS.

## Role inference

Each device gets a role (gateway, hypervisor, NAS, server, workstation, phone,
printer, media, camera, IoT, network gear, VM, unknown) with the **reasons**
that decided it and a confidence. Votes come from open ports (strongest),
mDNS service types, web UI titles, OUI vendor, hostname, OS guess and the MAC
itself (virtual-NIC OUIs such as Proxmox `bc:24:11`; the locally-administered
bit of randomized phone MACs). The default gateway and the NetScan host are
identified directly.

## Event feed

`/ws/events` and `/api/events`: every event has a monotonic `seq`, ISO
timestamp, `level` (debug/info/warning/error), `source` and message. The ring
buffer holds the last 5000 events; a reconnecting client asks for
`since=<last seq>` and is told how many were `dropped` if the buffer
overflowed. `info` and above are also written to `netscan.log` (rotating, 5 MiB
× 3 files).
