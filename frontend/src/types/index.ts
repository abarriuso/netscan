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
  tech?: string[]
  final_url?: string
  error?: string
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
  /** icmp | tcp/<port> (ICMP filtered) | '' (nothing answered) */
  rtt_source?: string
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
  p95_latency_ms?: number | null
  devices_measured?: number
}

export interface MetricHistoryPoint {
  t: string
  avg_latency_ms: number | null
  avg_quality: number | null
  avg_packet_loss_pct: number | null
  avg_throughput_mbps: number | null
  /** devices measured in that scan */
  devices: number
  /** of those, devices that answered ≥1 ICMP echo */
  devices_responding?: number
}

export interface ScanHistoryPoint {
  started_at: string
  duration_s: number
  total_devices: number
  network: string
}

export interface LiveDevice {
  mac: string
  ip: string
  name: string
  vendor: string
  trusted: boolean
  /** state after hysteresis (down only after `down_after` failed ticks) */
  up: boolean
  /** answered this very tick */
  answered?: boolean
  latency_ms: number | null
  /** probe that answered: icmp | tcp/<port> | arp | '' */
  method?: string
  failures?: number
  since?: string | null
  since_exact?: boolean
  recent_up_pct?: number | null
}

export interface LivePoint {
  t: string
  latency_ms: number | null
  online: number
  total?: number
  gateway_ms?: number | null
  wan_ms?: number | null
  wan_loss_pct?: number | null
  tick_ms?: number | null
}

export interface LiveSnapshot {
  series: LivePoint[]
  devices: LiveDevice[]
  online: number
  total: number
  interval_s: number
  updated_at: string | null
  enabled?: boolean
  down_after?: number
  icmp_backend?: string
  gateway_ip?: string | null
  wan_targets?: string[]
  tick_ms?: number | null
  monitoring_since?: string
}

export interface AlertRecord {
  id: number
  created_at: string
  kind:
    | 'new_device'
    | 'mac_changed'
    | 'device_down'
    | 'device_back'
    | 'ports_changed'
    | 'ip_conflict'
    | 'gateway_mac_changed'
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
  devices_new_24h?: number
  last_scan_duration_s?: number | null
  next_scan?: string | null
  last_scan_error?: string | null
}

export interface ToolInfo {
  available: boolean
  license: string
  purpose: string
}

export interface Capabilities {
  capabilities: Record<string, boolean>
  tools: Record<string, ToolInfo>
  runtime?: { icmp_backend: string; privileged: boolean; discovery: 'arp' | 'sweep' }
}

/** Individually-launchable scan stages — mirrors backend engine.ONLY_STAGES. */
export type ScanStage = 'arp' | 'mdns' | 'nmap' | 'rustscan' | 'nuclei' | 'whatweb' | 'testssl'

export interface ScanProgress {
  stage: string
  done: number
  total: number
  started_at?: string
  elapsed_s?: number
  error?: string
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
  /** seconds as AdGuard reports it (older backends) */
  avg_processing_time?: number
  avg_processing_time_ms?: number
  error?: string
}

export interface PiholeSummary {
  name: string
  host: string
  num_dns_queries?: number
  num_blocked_filtering?: number
  percent_blocked?: number
  domains_being_blocked?: number
  unique_clients?: number
  total_clients?: number | null
  error?: string
}

export interface CustomBookmark {
  id: number
  name: string
  url: string
  status: 'up' | 'down'
  logo_url: string | null
  http_status?: number | null
  ms?: number | null
  error?: string
}

// --- Integration settings (GET/POST/PATCH/DELETE /api/settings/integrations) --- //
export type IntegrationKind = 'proxmox' | 'truenas' | 'adguard' | 'pihole' | 'custom'

export interface IntegrationSetting {
  id?: number
  kind: IntegrationKind
  name: string
  enabled: boolean
  config: Record<string, string | number | boolean>
  logo_url?: string | null
  editable: boolean
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
  /** allocatable without swapping (bytes) */
  available_bytes?: number
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
  /** BYTES per second (legacy names) */
  up_bps: number
  down_bps: number
  tx_bytes_per_s?: number
  rx_bytes_per_s?: number
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
  scans_failed?: number
  last_scan_error?: string | null
  next_scan?: string | null
  privileged?: boolean
  events?: { last_seq: number; buffered: number; capacity: number; events_last_60s: number; by_source: Record<string, number> }
  gateway_ip?: string | null
  local_ip?: string | null
  network?: string | null
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

// --- Event feed (GET /api/events, WS /ws/events) + frontend telemetry ------ //
export type FeedLevel = 'debug' | 'info' | 'warning' | 'error'

export interface BusEvent {
  seq: number
  ts: string
  level: FeedLevel
  source: string
  msg: string
  data?: Record<string, unknown>
}

/** One line of the terminal dock: a backend event or a frontend one. */
export interface FeedLine {
  id: string
  origin: 'back' | 'front'
  seq?: number
  /** epoch ms */
  t: number
  ts: string
  level: FeedLevel
  source: string
  msg: string
  data?: Record<string, unknown>
}

// --- Uptime (GET /api/uptime) ------------------------------------------------ //
export interface UptimeWindow {
  availability_pct: number | null
  coverage_pct: number | null
  probes: number
}

export interface UptimeSlot {
  start: string
  availability_pct: number | null
  probes: number
  rtt_avg_ms: number | null
  rtt_min_ms: number | null
  rtt_max_ms: number | null
}

export interface Outage {
  start: string
  end: string | null
  duration_s: number
  ongoing: boolean
}

export interface UptimeDevice {
  mac: string
  ip: string
  name: string
  vendor: string
  trusted: boolean
  online: boolean
  state_since: string | null
  /** false = "at least since NetScan started watching" */
  state_since_exact?: boolean
  method: string
  latency_ms: number | null
  last_seen: string
  windows: Record<'1h' | '24h' | '7d' | '30d', UptimeWindow>
  timeline: UptimeSlot[]
  outages: Outage[]
  outages_24h: number
  outages_30d: number
  longest_outage_s: number | null
  mttr_s: number | null
}

export interface UptimeReport {
  generated_at: string
  hours: number
  slots: number
  slot_s: number
  interval_s: number
  definitions: Record<string, string>
  devices: UptimeDevice[]
}

// --- Network map / IP map ---------------------------------------------------- //
export type DeviceRole =
  | 'gateway'
  | 'netscan'
  | 'hypervisor'
  | 'nas'
  | 'server'
  | 'workstation'
  | 'mobile'
  | 'printer'
  | 'media'
  | 'camera'
  | 'iot'
  | 'network'
  | 'vm'
  | 'unknown'

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface MapNode {
  id: string
  mac: string
  ip: string
  name: string
  vendor: string
  role: DeviceRole
  role_reasons: string[]
  online: boolean
  method: string
  latency_ms: number | null
  ports: number[]
  web: number
  trusted: boolean
  risk_score: number
  risk_level: RiskLevel
  randomized_mac: boolean
  virtual: string
}

export interface NetworkMapData {
  network: string
  gateway_ip: string | null
  local_ip: string | null
  nodes: MapNode[]
  edges: { source: string; target: string; latency_ms: number | null }[]
  roles: Record<string, number>
}

export type IpState = 'network' | 'broadcast' | 'gateway' | 'self' | 'online' | 'offline' | 'free'

export interface IpMapData {
  network: string
  size: number
  usable: number
  used: number
  utilization_pct: number
  counts: Partial<Record<IpState, number>>
  cells: { ip: string; state: IpState; mac: string; name: string; last_seen: string | null }[]
}

// --- Security (GET /api/security) --------------------------------------------- //
export interface RiskFactor {
  id: string
  points: number
  severity: 'low' | 'medium' | 'high' | 'critical' | 'info'
  title: string
  evidence: string
  remediation: string
}

export interface RiskAssessment {
  score: number
  level: RiskLevel
  factors: RiskFactor[]
}

export interface SecurityDevice extends RiskAssessment {
  mac: string
  ip: string
  name: string
  vendor: string
  role: DeviceRole
  trusted: boolean
  online: boolean
}

export interface CertificateInfo {
  url: string
  ip: string
  subject: string
  issuer: string
  not_after: string
  days_remaining: number | null
  self_signed: boolean
  version: string
}

export interface Finding {
  tool?: string
  template: string
  severity: string
  name: string
  matched_at: string
}

export interface SecurityReport {
  summary: {
    devices: number
    by_level: Record<RiskLevel, number>
    avg_score: number | null
    network_level: RiskLevel | null
    untrusted: number
    randomized_macs: number
    findings: number
    certificates: number
    certs_expiring_30d: number
  }
  devices: SecurityDevice[]
  exposure: { port: number; devices: number }[]
  certificates: CertificateInfo[]
  findings: Finding[]
  conflicts: { ip: string; macs: string[] }[]
  gateway: { ip: string | null; mac: string; history: { at: string; detail: string }[] }
  scale: string
}

// --- Device profile & timeline -------------------------------------------------- //
export interface DeviceProfile {
  device: DeviceRecord
  classification: { role: DeviceRole; reasons: string[]; confidence: number }
  mac_info: { oui: string; locally_administered: boolean; randomized: boolean; virtual_platform: string }
  ports: PortInfo[]
  http: HttpInfo[]
  mdns_services: string[]
  findings: Finding[]
  risk: RiskAssessment
  live: LiveDevice | null
  scan_time: string | null
}

export interface TimelineEvent {
  at: string
  kind: string
  detail: string
  data: Record<string, unknown>
}

// --- Toolbox (POST /api/tools/*) ---------------------------------------------- //
export interface PingResult {
  target: string
  ip: string
  dns_ms: number
  count: number
  rtts_ms: (number | null)[]
  min_ms: number | null
  avg_ms: number | null
  max_ms: number | null
  stddev_ms: number | null
  jitter_ms: number | null
  loss_pct: number
}

export interface TraceResult {
  target: string
  ip: string
  reached: boolean
  hops: { ttl: number; ip: string | null; host: string; rtt_ms: number | null }[]
}

export interface DnsAnswer {
  name: string
  type: string
  ttl_s: number
  data: string
}

export interface DnsResult {
  name: string
  type: string
  server: string
  rcode: string
  ms: number | null
  authoritative?: boolean
  truncated?: boolean
  answers: DnsAnswer[]
}

export interface DnsBenchResult {
  name: string
  type: string
  results: {
    server: string
    median_ms: number | null
    min_ms: number | null
    answered: number
    rounds: number
    rcode: string | null
    answers: string[]
  }[]
}

export interface TcpResult {
  target: string
  ip: string
  port: number
  open: boolean
  connect_ms: (number | null)[]
  avg_ms: number | null
  banner: string
}

export interface PortScanResult {
  target: string
  scanned: number
  open: PortInfo[]
}

export interface HttpCheckResult {
  url: string
  ip: string
  http_version: string | null
  status: number | null
  reason: string
  headers: Record<string, string>
  body_bytes: number
  truncated: boolean
  tls_version: string | null
  timing: {
    dns_ms: number
    connect_ms: number
    tls_ms: number | null
    ttfb_ms: number
    transfer_ms: number
    total_ms: number
  }
  throughput_mbps: number | null
  security_headers_missing: string[]
}

export interface TlsResult {
  target: string
  ip: string
  port: number
  version: string | null
  cipher: string | null
  cipher_bits: number | null
  alpn: string | null
  connect_ms: number
  handshake_ms: number
  trusted: boolean
  trust_error: string
  certificate: {
    subject: string
    issuer: string
    san: string[]
    not_before: string
    not_after: string
    key?: string
    signature_algorithm?: string
    serial?: string
    days_remaining?: number
    self_signed?: boolean
  }
}

export interface SubnetResult {
  network: string
  prefix: number
  cidr: string
  netmask: string
  wildcard: string
  broadcast: string | null
  addresses: number
  usable_hosts: number
  first_host: string
  last_host: string
  private: boolean
  version: number
}

export interface MacResult {
  mac: string
  vendor: string
  oui: string
  locally_administered: boolean
  randomized: boolean
  virtual_platform: string
}
