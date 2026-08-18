// NetScan API client
import type {
  AdGuardSummary,
  AlertRecord,
  Capabilities,
  DeviceRecord,
  Overview,
  ProxmoxSummary,
  TrueNASSummary,
} from '@/types'

const BASE = import.meta.env.VITE_API_URL ?? ''

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`)
  if (!resp.ok) throw new Error(`${path}: ${resp.status}`)
  return resp.json() as Promise<T>
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!resp.ok) throw new Error(`${path}: ${resp.status}`)
  return resp.json() as Promise<T>
}

export const api = {
  overview: () => get<Overview>('/api/overview'),
  capabilities: () => get<Capabilities>('/api/capabilities'),
  devices: () => get<DeviceRecord[]>('/api/devices'),
  alerts: (unack = false) => get<AlertRecord[]>(`/api/alerts${unack ? '?unacknowledged=true' : ''}`),
  proxmox: () => get<ProxmoxSummary[]>('/api/integrations/proxmox'),
  truenas: () => get<TrueNASSummary[]>('/api/integrations/truenas'),
  adguard: () => get<AdGuardSummary[]>('/api/integrations/adguard'),
  startScan: (full = true) => send<{ status: string }>('/api/scans', 'POST', { full }),
  ackAlert: (id: number) => send<{ ok: boolean }>(`/api/alerts/${id}/ack`, 'POST'),
  setTrusted: (mac: string, trusted: boolean) =>
    send<{ ok: boolean }>(`/api/devices/${encodeURIComponent(mac)}`, 'PATCH', { trusted }),
  wake: (mac: string) =>
    send<{ ok: boolean }>(`/api/devices/${encodeURIComponent(mac)}/wake`, 'POST'),
  latestScanRaw: () => get<{ started_at: string; result: string }>('/api/scans/latest'),
}

export interface LatestScanDevice {
  ip: string
  hostname: string
  mdns_name: string
  http: { url: string; status_code: number; title: string; server: string; tls: {
    issuer: string; days_remaining: number | null; self_signed: boolean; version: string
  } | null }[]
}

export interface LatestScan {
  started_at: string
  duration_s: number
  total_devices: number
  devices: LatestScanDevice[]
  vulnerabilities: { template: string; severity: string; name: string; matched_at: string }[]
}

export async function fetchLatestScan(): Promise<LatestScan | null> {
  try {
    const raw = await api.latestScanRaw()
    return JSON.parse(raw.result) as LatestScan
  } catch {
    return null
  }
}

export function progressSocket(onMessage: (p: { stage: string; done: number; total: number }) => void) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const host = BASE ? new URL(BASE).host : location.host
  const ws = new WebSocket(`${proto}://${host}/ws/progress`)
  ws.onmessage = (ev) => {
    try {
      onMessage(JSON.parse(ev.data))
    } catch {
      /* ignore malformed frames */
    }
  }
  return ws
}
