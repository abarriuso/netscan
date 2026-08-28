// NetScan API client
import type {
  AdGuardSummary,
  AlertRecord,
  Capabilities,
  DeviceMetrics,
  DeviceRecord,
  MetricSamplePoint,
  MetricsSummary,
  Overview,
  ProxmoxSummary,
  ScanStage,
  SystemStatus,
  TrueNASSummary,
} from '@/types'

const BASE = import.meta.env.VITE_API_URL ?? ''

/** Optional API token (only needed if the backend has NETSCAN_API_TOKEN set).
 *  Stored in localStorage after the first 401 prompt. */
function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('netscan_token')
  return token ? { 'X-API-Key': token } : {}
}

async function ensureAuth(res: Response): Promise<void> {
  if (res.status === 401) {
    const token = window.prompt('Este NetScan requiere token (NETSCAN_API_TOKEN). Introdúcelo:')
    if (token) {
      localStorage.setItem('netscan_token', token)
      return
    }
  }
}

async function get<T>(path: string): Promise<T> {
  let resp = await fetch(`${BASE}${path}`, { headers: authHeaders() })
  if (resp.status === 401) {
    await ensureAuth(resp)
    resp = await fetch(`${BASE}${path}`, { headers: authHeaders() })
  }
  if (!resp.ok) throw new Error(`${path}: ${resp.status}`)
  return resp.json() as Promise<T>
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const make = () =>
    fetch(`${BASE}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  let resp = await make()
  if (resp.status === 401) {
    await ensureAuth(resp)
    resp = await make()
  }
  if (!resp.ok) throw new Error(`${path}: ${resp.status}`)
  return resp.json() as Promise<T>
}

export const api = {
  overview: () => get<Overview>('/api/overview'),
  system: () => get<SystemStatus>('/api/system'),
  metricsSummary: () => get<MetricsSummary>('/api/metrics/summary'),
  deviceMetrics: (mac: string, limit = 60) =>
    get<{ mac: string; samples: MetricSamplePoint[] }>(
      `/api/devices/${encodeURIComponent(mac)}/metrics?limit=${limit}`,
    ),
  speedtest: (mac: string, throughput = false) =>
    send<{ mac: string; ip: string; metrics: DeviceMetrics }>(
      `/api/devices/${encodeURIComponent(mac)}/speedtest?throughput=${throughput}`,
      'POST',
    ),
  capabilities: () => get<Capabilities>('/api/capabilities'),
  logs: (lines = 300) => get<{ path: string; lines: string[] }>(`/api/logs?lines=${lines}`),
  devices: () => get<DeviceRecord[]>('/api/devices'),
  alerts: (unack = false) => get<AlertRecord[]>(`/api/alerts${unack ? '?unacknowledged=true' : ''}`),
  proxmox: () => get<ProxmoxSummary[]>('/api/integrations/proxmox'),
  truenas: () => get<TrueNASSummary[]>('/api/integrations/truenas'),
  adguard: () => get<AdGuardSummary[]>('/api/integrations/adguard'),
  startScan: (opts: { full?: boolean; only?: ScanStage } = {}) =>
    send<{ status: string }>('/api/scans', 'POST', opts),
  ackAlert: (id: number) => send<{ ok: boolean }>(`/api/alerts/${id}/ack`, 'POST'),
  setTrusted: (mac: string, trusted: boolean) =>
    send<{ ok: boolean }>(`/api/devices/${encodeURIComponent(mac)}`, 'PATCH', { trusted }),
  wake: (mac: string) =>
    send<{ ok: boolean }>(`/api/devices/${encodeURIComponent(mac)}/wake`, 'POST'),
  latestScanRaw: () => get<{ started_at: string; result: Omit<LatestScan, 'started_at'> }>('/api/scans/latest'),
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
    return { started_at: raw.started_at, ...raw.result }
  } catch {
    return null
  }
}

export function progressSocket(onMessage: (p: { stage: string; done: number; total: number }) => void) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const host = BASE ? new URL(BASE).host : location.host
  const token = localStorage.getItem('netscan_token')
  const qs = token ? `?token=${encodeURIComponent(token)}` : ''
  const ws = new WebSocket(`${proto}://${host}/ws/progress${qs}`)
  ws.onmessage = (ev) => {
    try {
      onMessage(JSON.parse(ev.data))
    } catch {
      /* ignore malformed frames */
    }
  }
  return ws
}
