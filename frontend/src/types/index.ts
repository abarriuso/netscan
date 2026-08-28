// NetScan API types — mirror of backend/src/netscan/models.py

export interface PortInfo {
  port: number
  service: string
  version: string
}

export interface TlsInfo {
  issuer: string
  subject: string
  not_before: string
  not_after: string
  days_remaining: number | null
  self_signed: boolean
  version: string
}

export interface HttpInfo {
  url: string
  status_code: number
  title: string
  server: string
  tls: TlsInfo | null
}

export interface DeviceRecord {
  id: number
  mac: string
  ip: string
  hostname: string
  vendor: string
  mdns_name: string
  os_guess: string
  notes: string
  trusted: boolean
  first_seen: string
  last_seen: string
  last_latency_ms: number | null
  open_ports_json: string
  online: boolean
  // Speed / quality metrics (see backend scanner/speed.py)
  jitter_ms: number | null
  packet_loss_pct: number | null
  tcp_connect_avg_ms: number | null
  throughput_mbps: number | null
  quality: number | null
}

export interface DeviceMetrics {
  latency_avg_ms: number | null
  latency_min_ms: number | null
  latency_max_ms: number | null
  jitter_ms: number | null
  packet_loss_pct: number | null
  tcp_connect_ms: Record<string, number>
  tcp_connect_avg_ms: number | null
  throughput_mbps: number | null
  throughput_port: number | null
  quality: number | null
  measured_at: string | null
}

export interface MetricSamplePoint {
  t: string
  latency_ms: number | null
  jitter_ms: number | null
  packet_loss_pct: number | null
  tcp_connect_avg_ms: number | null
  throughput_mbps: number | null
  quality: number | null
}

export interface MetricsSummary {
  devices_total: number
  devices_online: number
  avg_latency_ms: number | null
  avg_quality: number | null
  avg_packet_loss_pct: number | null
  max_throughput_mbps: number | null
  worst_quality: number | null
}

export interface AlertRecord {
  id: number
  created_at: string
  kind: 'new_device' | 'mac_changed' | 'device_down' | 'device_back'
  device_mac: string
  device_ip: string
  detail: string
  acknowledged: boolean
}

export interface Overview {
  version: string
  devices_total: number
  devices_online: number
  devices_untrusted: number
  alerts_unacknowledged: number
  last_scan: string | null
  capabilities: Record<string, boolean>
  metrics?: MetricsSummary
}

export interface ToolInfo {
  available: boolean
  license: string
  purpose: string
}

export interface Capabilities {
  capabilities: Record<string, boolean>
  tools: Record<string, ToolInfo>
}

/** Individually-launchable scan stages — mirrors backend engine.ONLY_STAGES. */
export type ScanStage = 'arp' | 'mdns' | 'nmap' | 'rustscan' | 'nuclei'

export interface ScanProgress {
  stage: string
  done: number
  total: number
}

export interface ProxmoxGuest {
  vmid: number
  name?: string
  type: 'qemu' | 'lxc'
  status: string
  cpu?: number
  maxcpu?: number
  mem?: number
  maxmem?: number
  node?: string
}

export interface ProxmoxNode {
  node: string
  status: string
  cpu?: number
  maxcpu?: number
  mem?: number
  maxmem?: number
  uptime?: number
}

export interface ProxmoxSummary {
  name: string
  host: string
  version?: string
  nodes?: ProxmoxNode[]
  guests?: ProxmoxGuest[]
  guests_running?: number
  guests_total?: number
  error?: string
}

export interface TrueNASPool {
  name: string
  status: string
  healthy: boolean
  size?: number
  allocated?: number
  free?: number
}

export interface TrueNASDisk {
  name: string
  model?: string
  serial?: string
  size?: number
  type?: string
}

export interface TrueNASSummary {
  name: string
  host: string
  version?: string
  hostname?: string
  uptime_seconds?: number
  loadavg?: number[]
  cores?: number
  pools?: TrueNASPool[]
  pools_healthy?: number
  pools_total?: number
  disks?: TrueNASDisk[]
  alerts?: { formatted?: string; level?: string }[]
  error?: string
}

export interface AdGuardClientInfo {
  name: string
  ip: string[]
}

export interface AdGuardSummary {
  name: string
  host: string
  version?: string
  clients?: AdGuardClientInfo[]
  num_dns_queries?: number
  num_blocked_filtering?: number
  avg_processing_time?: number
  error?: string
}

// --- System / server status (GET /api/system) ---------------------------- //
export interface HostInfo {
  hostname: string
  os: string
  os_release: string
  os_version: string
  arch: string
  boot_time: string | null
  uptime_seconds: number | null
  cpu_model: string
}

export interface CpuInfo {
  available: boolean
  percent?: number
  per_core?: number[]
  logical?: number
  physical?: number | null
  freq_mhz?: number | null
  freq_max_mhz?: number | null
  load_avg?: number[] | null
}

export interface MemoryInfo {
  available: boolean
  total?: number
  used?: number
  free?: number
  percent?: number
  swap_total?: number
  swap_used?: number
  swap_percent?: number
}

export interface DiskInfo {
  mount: string
  device: string
  fstype: string
  total: number
  used: number
  free: number
  percent: number
}

export interface NetIface {
  name: string
  is_up: boolean
  speed_mbps: number | null
  mtu: number
  ipv4: string
  mac: string
  bytes_sent: number
  bytes_recv: number
  up_bps: number
  down_bps: number
}

export interface ProcessInfo {
  pid: number
  uptime_seconds: number
  python: string
  executable: string
  cpu_percent?: number
  rss?: number | null
  threads?: number
  open_files?: number
  connections?: number
  create_time?: string
}

export interface FrontendStatus {
  built: boolean
  path: string | null
  files?: number
  size_bytes?: number
  built_at?: string | null
  served_by_backend?: boolean
}

export interface ServerInfo {
  version: string
  uptime_seconds: number
  requests_served: number
  scans_completed: number
  last_scan_duration_s: number | null
  scan_in_progress: boolean
  ws_clients: number
  scheduler_interval_min: number
  api_host: string
  api_port: number
  auth_enabled: boolean
  db_url: string
}

export interface SystemStatus {
  timestamp: string
  host: HostInfo
  cpu: CpuInfo
  memory: MemoryInfo
  disks: DiskInfo[]
  network: { available: boolean; interfaces: NetIface[] }
  process: ProcessInfo
  frontend: FrontendStatus
  psutil: boolean
  server: ServerInfo
}
