// NetScan API client
import type {
  AdGuardSummary,
  AlertRecord,
  Capabilities,
  CustomBookmark,
  DeviceMetrics,
  DeviceProfile,
  DeviceRecord,
  DnsBenchResult,
  DnsResult,
  HttpCheckResult,
  IntegrationKind,
  IntegrationSetting,
  IpMapData,
  LiveSnapshot,
  MacResult,
  MetricHistoryPoint,
  MetricSamplePoint,
  MetricsSummary,
  NetworkMapData,
  Overview,
  PiholeSummary,
  PingResult,
  PortScanResult,
  ProxmoxSummary,
  ScanHistoryPoint,
  ScanStage,
  SecurityReport,
  SubnetResult,
  SystemStatus,
  TcpResult,
  TimelineEvent,
  TlsResult,
  TraceResult,
  TrueNASSummary,
  UptimeDevice,
  UptimeReport,
} from '@/types'
import { logFront } from './telemetry'

const BASE = import.meta.env.VITE_API_URL ?? ''

/** Optional API token (only needed if the backend has NETSCAN_API_TOKEN set).
 *  Stored in localStorage; entered through <TokenDialog> (see components/TokenDialog.tsx). */
function currentToken(): string {
  return localStorage.getItem('netscan_token') ?? ''
}

function authHeaders(token = currentToken()): Record<string, string> {
  return token ? { 'X-API-Key': token } : {}
}

export function hasToken(): boolean {
  return !!currentToken()
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
// The token value ('' = none) the server last turned down. While the saved
// token is still that one, sending it again can only fail — and each failure
// counts against the server's brute-force limiter — so requests wait for a
// new token instead.
let rejectedToken: string | null = null
// The user chose "Not now" for the rejected token: stop reopening the dialog
// and fail requests locally until they save a token (header key button).
let authDismissed = false
let tokenSaved: Promise<void> | null = null
let resolveTokenSaved: (() => void) | null = null

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

/** Accept the token however it was copied out of netscan.env: the whole
 *  `NETSCAN_API_TOKEN=...` line or a quoted value would otherwise be saved
 *  verbatim and rejected on every request. */
export function normalizeToken(raw: string): string {
  return raw
    .trim()
    .replace(/^NETSCAN_API_TOKEN\s*=\s*/, '')
    .replace(/^(['"])(.*)\1$/, '$2')
    .trim()
}

/** Called by <TokenDialog> when the user submits a value. */
export function submitToken(token: string) {
  localStorage.setItem('netscan_token', normalizeToken(token))
  // An explicit save is worth one more try even if it is the value the
  // server rejected before (the server's token may have been changed back).
  rejectedToken = null
  authDismissed = false
  resolvePending?.()
  pendingAuth = null
  resolvePending = null
  resolveTokenSaved?.()
  tokenSaved = null
  resolveTokenSaved = null
}

/** Called by <TokenDialog> when the user dismisses it without one — queued
 *  requests fail with a normal, visible panel error instead of hanging, and
 *  the dialog stays closed until the user opens it from the header. */
export function cancelAuth() {
  authDismissed = true
  resolvePending?.()
  pendingAuth = null
  resolvePending = null
}

export function clearToken() {
  localStorage.removeItem('netscan_token')
}

/** True while the saved token (or the lack of one) is the one the server
 *  already rejected — sending it again would just be another failed login. */
export function tokenRejected(): boolean {
  return rejectedToken !== null && rejectedToken === currentToken()
}

/** Record that the server turned down `token` (a 401/429 for it). Ignored
 *  when a newer token was saved while that request was in flight. */
export function markTokenRejected(token: string): void {
  if (token !== currentToken()) return
  rejectedToken = token
  if (!authDismissed) void ensureAuth()
}

/** Resolves the next time the user saves a token — for the sockets, which
 *  must not retry with a rejected one in the meantime. */
export function waitForNewToken(): Promise<void> {
  if (!tokenSaved) {
    tokenSaved = new Promise((resolve) => {
      resolveTokenSaved = resolve
    })
  }
  return tokenSaved
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

/** fetch() + one telemetry line per request: method, path, status, wall
 *  time measured in the browser (network + server) and response size. */
async function traced(method: string, path: string, init: RequestInit): Promise<Response> {
  const start = performance.now()
  try {
    const resp = await fetch(`${BASE}${path}`, init)
    const ms = performance.now() - start
    const size = Number(resp.headers?.get?.('content-length') ?? NaN)
    logFront(
      'http',
      `${method} ${path} → ${resp.status} · ${ms < 100 ? ms.toFixed(1) : Math.round(ms)} ms` +
        (Number.isFinite(size) ? ` · ${(size / 1024).toFixed(1)} KiB` : ''),
      resp.ok ? 'debug' : 'warning',
      { method, path, status: resp.status, ms: Math.round(ms * 100) / 100 },
    )
    return resp
  } catch (e) {
    logFront('http', `${method} ${path} → network error: ${(e as Error).message}`, 'error', { method, path })
    throw e
  }
}

function authRequiredError(path: string): Error {
  const err = new Error('Invalid or missing API token') as Error & { status?: number; path?: string }
  err.status = 401
  err.path = path
  return err
}

/** traced() with the saved token, and one auth policy for every caller:
 *  wait while the token dialog is open; never re-send a token the server
 *  already rejected (prompt for a new one, or fail locally after "Not now");
 *  and retry — instead of prompting again — a 401 for a token that was
 *  replaced while the request was in flight. A slow or stalled server
 *  answers the requests sent before the user typed the token only after it
 *  was saved; treating those late 401s as "bad token" reopened the dialog
 *  right after a correct one was entered. A 429 is the server's limiter on
 *  failed tokens, so it counts as a rejection too. */
async function authorized(
  method: string,
  path: string,
  init: (headers: Record<string, string>) => RequestInit,
): Promise<Response> {
  for (;;) {
    if (pendingAuth) await pendingAuth
    const token = currentToken()
    if (token === rejectedToken) {
      if (authDismissed) throw authRequiredError(path)
      await ensureAuth()
      continue
    }
    const resp = await traced(method, path, init(authHeaders(token)))
    if (resp.status !== 401 && resp.status !== 429) return resp
    markTokenRejected(token)
  }
}

async function get<T>(path: string): Promise<T> {
  const cached = _cache.get(path)
  if (cached && Date.now() - cached.at < CACHE_TTL_MS) return cached.value as T
  const existing = _inflight.get(path)
  if (existing) return existing as Promise<T>
  const run = (async () => {
    const resp = await authorized('GET', path, (headers) => ({ headers }))
    if (!resp.ok) throw await errorFromResponse(resp, path)
    const value = await resp.json()
    _cache.set(path, { at: Date.now(), value })
    return value
  })().finally(() => _inflight.delete(path))
  _inflight.set(path, run)
  return run as Promise<T>
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const resp = await authorized(method, path, (headers) => ({
    method,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  }))
  if (!resp.ok) throw await errorFromResponse(resp, path)
  // A successful mutation changes server state — drop cached GETs so the next
  // poll reflects it immediately instead of serving up to CACHE_TTL_MS stale.
  invalidateCache()
  return resp.json() as Promise<T>
}

/** Absolute URL for a download link (exports): carries the token in a
 *  header-less context only if the server has none — otherwise the export
 *  is fetched and saved as a Blob (see downloadExport). */
export async function downloadExport(format: 'csv' | 'json'): Promise<void> {
  const path = `/api/export/devices?format=${format}`
  const resp = await authorized('GET', path, (headers) => ({ headers }))
  if (!resp.ok) throw await errorFromResponse(resp, path)
  const blob = await resp.blob()
  const disposition = resp.headers.get('content-disposition') ?? ''
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `netscan-devices.${format}`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  logFront('ui', `exported the inventory as ${name} (${(blob.size / 1024).toFixed(1)} KiB)`)
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
  scanProgress: () =>
    get<{ stage: string; done: number; total: number; elapsed_s?: number; error?: string }>('/api/scans/progress'),
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
  ackAllAlerts: () => send<{ acknowledged: number }>('/api/alerts/ack-all', 'POST'),
  setNotes: (mac: string, notes: string) =>
    send<{ ok: boolean }>(`/api/devices/${encodeURIComponent(mac)}`, 'PATCH', { notes }),

  // -- Cross-source views --
  uptime: (hours = 24, slots = 48) => get<UptimeReport>(`/api/uptime?hours=${hours}&slots=${slots}`),
  deviceUptime: (mac: string, hours = 24, slots = 96) =>
    get<UptimeReport & { device: UptimeDevice }>(
      `/api/devices/${encodeURIComponent(mac)}/uptime?hours=${hours}&slots=${slots}`,
    ),
  deviceProfile: (mac: string) => get<DeviceProfile>(`/api/devices/${encodeURIComponent(mac)}/profile`),
  deviceTimeline: (mac: string) =>
    get<{ mac: string; events: TimelineEvent[] }>(`/api/devices/${encodeURIComponent(mac)}/timeline`),
  map: () => get<NetworkMapData>('/api/map'),
  ipMap: (network?: string) =>
    get<IpMapData>(`/api/ipmap${network ? `?network=${encodeURIComponent(network)}` : ''}`),
  security: () => get<SecurityReport>('/api/security'),

  // -- Toolbox (run on the NetScan host) --
  tools: {
    ping: (target: string, count = 5) => send<PingResult>('/api/tools/ping', 'POST', { target, count }),
    traceroute: (target: string, max_hops = 20) =>
      send<TraceResult>('/api/tools/traceroute', 'POST', { target, max_hops }),
    dns: (name: string, type: string, server: string) =>
      send<DnsResult>('/api/tools/dns', 'POST', { name, type, server }),
    dnsBench: (name: string, type = 'A', servers: string[] = []) =>
      send<DnsBenchResult>('/api/tools/dns-bench', 'POST', { name, type, servers, rounds: 3 }),
    tcp: (target: string, port: number) => send<TcpResult>('/api/tools/tcp', 'POST', { target, port, count: 3 }),
    portscan: (target: string, ports: string) =>
      send<PortScanResult>('/api/tools/portscan', 'POST', { target, ports }),
    http: (url: string) => send<HttpCheckResult>('/api/tools/http', 'POST', { url }),
    tls: (target: string, port: number) => send<TlsResult>('/api/tools/tls', 'POST', { target, port }),
    subnet: (cidr: string) => send<SubnetResult>('/api/tools/subnet', 'POST', { cidr }),
    mac: (mac: string) => send<MacResult>('/api/tools/mac', 'POST', { mac }),
  },
  setTrusted: (mac: string, trusted: boolean) =>
    send<{ ok: boolean }>(`/api/devices/${encodeURIComponent(mac)}`, 'PATCH', { trusted }),
  wake: (mac: string) =>
    send<{ ok: boolean; broadcast?: string }>(`/api/devices/${encodeURIComponent(mac)}/wake`, 'POST'),
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
    const path = `/api/settings/integrations/${id}/logo`
    // No Content-Type — the browser sets the multipart boundary.
    const resp = await authorized('POST', path, (headers) => ({ method: 'POST', headers, body: form }))
    if (!resp.ok) throw await errorFromResponse(resp, path)
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
    // Optional: scans persisted before these fields existed won't have them.
    tech?: string[]
    final_url?: string
    error?: string
    tls: { issuer: string; days_remaining: number | null; self_signed: boolean; version: string } | null
  }[]
}

export interface LatestScan {
  started_at: string
  duration_s: number
  total_devices: number
  devices: LatestScanDevice[]
  vulnerabilities: { tool?: string; template: string; severity: string; name: string; matched_at: string }[]
  discovery_method?: string
  mode?: string
  skipped?: string[]
  gateway_ip?: string
  stage_timings?: { stage: string; duration_s: number }[]
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
  const token = currentToken()
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
