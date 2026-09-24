// NetScan API client
import type {
  AdGuardSummary,
  AlertRecord,
  Capabilities,
  CustomBookmark,
  DeviceMetrics,
  DeviceRecord,
  IntegrationKind,
  IntegrationSetting,
  LiveSnapshot,
  MetricHistoryPoint,
  MetricSamplePoint,
  MetricsSummary,
  Overview,
  PiholeSummary,
  ProxmoxSummary,
  ScanHistoryPoint,
  ScanStage,
  SystemStatus,
  TrueNASSummary,
} from '@/types'

const BASE = import.meta.env.VITE_API_URL ?? ''

/** Optional API token (only needed if the backend has NETSCAN_API_TOKEN set).
 *  Stored in localStorage; entered through <TokenDialog> (see components/TokenDialog.tsx). */
function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('netscan_token')
  return token ? { 'X-API-Key': token } : {}
}

export function hasToken(): boolean {
  return !!localStorage.getItem('netscan_token')
}

type AuthListener = () => void
const authListeners = new Set<AuthListener>()
// A single in-flight "waiting for the user to type a token" gate, shared by
// every concurrent caller — without this, every panel's own poll tick would
// independently hit a 401, and the resulting flurry of parallel retries used
// to trip the backend's brute-force rate limiter (429) before the user even
// finished reading the dialog. Confirmed live: a fleet of ~10 poll hooks all
// failing every 2.5-60s each read as a separate "auth failure" to the server.
let pendingAuth: Promise<void> | null = null
let resolvePending: (() => void) | null = null

/** Subscribe to "a token is needed" events — <TokenDialog> uses this to auto-open. */
export function onAuthRequired(cb: AuthListener): () => void {
  authListeners.add(cb)
  return () => authListeners.delete(cb)
}

// Separate, non-blocking "open the dialog so the user can change the saved
// token" trigger — e.g. the settings button in the header. Unlike
// onAuthRequired, opening this way never gates any in-flight request.
const manualOpenListeners = new Set<AuthListener>()
export function onTokenDialogRequested(cb: AuthListener): () => void {
  manualOpenListeners.add(cb)
  return () => manualOpenListeners.delete(cb)
}
export function requestTokenDialog() {
  manualOpenListeners.forEach((cb) => cb())
}

/** Called by <TokenDialog> when the user submits a value. */
export function submitToken(token: string) {
  localStorage.setItem('netscan_token', token)
  resolvePending?.()
  pendingAuth = null
  resolvePending = null
}

/** Called by <TokenDialog> when the user dismisses it without one — lets
 *  queued requests proceed (and fail with a normal, visible panel error)
 *  instead of hanging forever. */
export function cancelAuth() {
  resolvePending?.()
  pendingAuth = null
  resolvePending = null
}

export function clearToken() {
  localStorage.removeItem('netscan_token')
}

function ensureAuth(): Promise<void> {
  if (!pendingAuth) {
    pendingAuth = new Promise((resolve) => {
      resolvePending = resolve
    })
    authListeners.forEach((cb) => cb())
  }
  return pendingAuth
}

// --- Lightweight GET layer: in-flight dedup + a short TTL cache. Several
// panels poll independently and some hit the same endpoint (/api/devices is
// read by both the table and the analytics panel); without this, a scan-done
// refresh fires the same request several times at once. Concurrent callers for
// one path share a single request, and a resolved response is reused for
// CACHE_TTL_MS so near-simultaneous polls don't re-fetch. Mutations (see
// `send`) clear the cache so a change is visible on the next poll. ---
const CACHE_TTL_MS = 2000
const _inflight = new Map<string, Promise<unknown>>()
const _cache = new Map<string, { at: number; value: unknown }>()

export function invalidateCache(): void {
  _cache.clear()
}

/** Turn a failed Response into a useful Error. The backend answers errors as
 *  `{"detail": "..."}` (FastAPI convention); surface that human message instead
 *  of a bare status code so panels and toasts can show what actually went wrong.
 *  Falls back to a status-based message when the body isn't the expected shape
 *  (network layer, proxy error page, empty 500). Exported for unit testing. */
export async function errorFromResponse(resp: Response, path: string): Promise<Error> {
  let detail = ''
  try {
    const data = await resp.clone().json()
    if (data && typeof data.detail === 'string') detail = data.detail
    else if (Array.isArray(data?.detail)) {
      // FastAPI 422 validation errors: [{loc, msg, ...}, ...]
      detail = data.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ')
    }
  } catch {
    /* not JSON — fall through to the status-based message */
  }
  if (!detail) {
    detail =
      resp.status >= 500
        ? 'internal server error'
        : resp.status === 0
          ? 'no connection'
          : (resp.statusText || `HTTP ${resp.status}`)
  }
  const err = new Error(detail) as Error & { status?: number; path?: string }
  err.status = resp.status
  err.path = path
  return err
}

async function get<T>(path: string): Promise<T> {
  const cached = _cache.get(path)
  if (cached && Date.now() - cached.at < CACHE_TTL_MS) return cached.value as T
  const existing = _inflight.get(path)
  if (existing) return existing as Promise<T>
  const run = (async () => {
    if (pendingAuth) await pendingAuth
    let resp = await fetch(`${BASE}${path}`, { headers: authHeaders() })
    if (resp.status === 401) {
      await ensureAuth()
      resp = await fetch(`${BASE}${path}`, { headers: authHeaders() })
    }
    if (!resp.ok) throw await errorFromResponse(resp, path)
    const value = await resp.json()
    _cache.set(path, { at: Date.now(), value })
    return value
  })().finally(() => _inflight.delete(path))
  _inflight.set(path, run)
  return run as Promise<T>
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const make = () =>
    fetch(`${BASE}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  if (pendingAuth) await pendingAuth
  let resp = await make()
  if (resp.status === 401) {
    await ensureAuth()
    resp = await make()
  }
  if (!resp.ok) throw await errorFromResponse(resp, path)
  // A successful mutation changes server state — drop cached GETs so the next
  // poll reflects it immediately instead of serving up to CACHE_TTL_MS stale.
  invalidateCache()
  return resp.json() as Promise<T>
}

export const api = {
  overview: () => get<Overview>('/api/overview'),
  system: () => get<SystemStatus>('/api/system'),
  metricsSummary: () => get<MetricsSummary>('/api/metrics/summary'),
  metricsHistory: (limit = 200) => get<{ points: MetricHistoryPoint[] }>(`/api/metrics/history?limit=${limit}`),
  scanHistory: (limit = 100) => get<{ scans: ScanHistoryPoint[] }>(`/api/scans/history?limit=${limit}`),
  live: () => get<LiveSnapshot>('/api/live'),
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
  scanProgress: () => get<{ stage: string; done: number; total: number }>('/api/scans/progress'),
  devices: () => get<DeviceRecord[]>('/api/devices'),
  alerts: (unack = false) => get<AlertRecord[]>(`/api/alerts${unack ? '?unacknowledged=true' : ''}`),
  proxmox: () => get<ProxmoxSummary[]>('/api/integrations/proxmox'),
  truenas: () => get<TrueNASSummary[]>('/api/integrations/truenas'),
  adguard: () => get<AdGuardSummary[]>('/api/integrations/adguard'),
  pihole: () => get<PiholeSummary[]>('/api/integrations/pihole'),
  customBookmarks: () => get<CustomBookmark[]>('/api/integrations/custom'),
  startScan: (opts: { full?: boolean; only?: ScanStage } = {}) =>
    send<{ status: string }>('/api/scans', 'POST', opts),
  ackAlert: (id: number) => send<{ ok: boolean }>(`/api/alerts/${id}/ack`, 'POST'),
  setTrusted: (mac: string, trusted: boolean) =>
    send<{ ok: boolean }>(`/api/devices/${encodeURIComponent(mac)}`, 'PATCH', { trusted }),
  wake: (mac: string) =>
    send<{ ok: boolean }>(`/api/devices/${encodeURIComponent(mac)}/wake`, 'POST'),
  latestScanRaw: () => get<{ started_at: string; result: Omit<LatestScan, 'started_at'> }>('/api/scans/latest'),

  // -- Integration settings (add/edit/remove from the dashboard) --
  listIntegrationSettings: () => get<IntegrationSetting[]>('/api/settings/integrations'),
  createIntegration: (kind: IntegrationKind, name: string, config: Record<string, unknown>, enabled = true) =>
    send<IntegrationSetting>('/api/settings/integrations', 'POST', { kind, name, config, enabled }),
  updateIntegration: (
    id: number,
    patch: { name?: string; enabled?: boolean; config?: Record<string, unknown> },
  ) => send<IntegrationSetting>(`/api/settings/integrations/${id}`, 'PATCH', patch),
  deleteIntegration: (id: number) => send<{ ok: boolean }>(`/api/settings/integrations/${id}`, 'DELETE'),
  uploadIntegrationLogo: async (id: number, file: File): Promise<{ ok: boolean; logo_url: string }> => {
    const form = new FormData()
    form.append('file', file)
    if (pendingAuth) await pendingAuth
    let resp = await fetch(`${BASE}/api/settings/integrations/${id}/logo`, {
      method: 'POST',
      headers: authHeaders(), // no Content-Type — the browser sets the multipart boundary
      body: form,
    })
    if (resp.status === 401) {
      await ensureAuth()
      resp = await fetch(`${BASE}/api/settings/integrations/${id}/logo`, {
        method: 'POST',
        headers: authHeaders(),
        body: form,
      })
    }
    if (!resp.ok) throw await errorFromResponse(resp, `/api/settings/integrations/${id}/logo`)
    return resp.json()
  },
}

export interface LatestScanDevice {
  ip: string
  hostname: string
  mdns_name: string
  http: {
    url: string
    status_code: number
    title: string
    server: string
    // Optional: scans persisted before this field existed won't have it.
    tech?: string[]
    tls: { issuer: string; days_remaining: number | null; self_signed: boolean; version: string } | null
  }[]
}

export interface LatestScan {
  started_at: string
  duration_s: number
  total_devices: number
  devices: LatestScanDevice[]
  vulnerabilities: { tool?: string; template: string; severity: string; name: string; matched_at: string }[]
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
