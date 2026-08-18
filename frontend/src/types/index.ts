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
