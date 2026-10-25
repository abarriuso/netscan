// Backend event feed: one shared WebSocket to /ws/events for the whole app
// (terminal dock, header progress detail...). On connect it asks for
// everything after the last sequence number it has, so a reconnect never
// leaves a hole; while the socket is down it falls back to HTTP polling of
// /api/events and says so (state "polling").
import type { BusEvent, FeedLine } from '@/types'
import { logFront } from './telemetry'

export type StreamState = 'connecting' | 'live' | 'polling' | 'offline'

const CAPACITY = 5000
const BASE = import.meta.env.VITE_API_URL ?? ''

let lines: FeedLine[] = []
let lastSeq = 0
let state: StreamState = 'connecting'
let ws: WebSocket | null = null
let refs = 0
let retryTimer: ReturnType<typeof setTimeout> | undefined
let pollTimer: ReturnType<typeof setInterval> | undefined
let backoff = 1000
const listeners = new Set<() => void>()
let scheduled = false

function notify() {
  if (scheduled) return
  scheduled = true
  queueMicrotask(() => {
    scheduled = false
    listeners.forEach((l) => l())
  })
}

function setState(next: StreamState) {
  if (state === next) return
  state = next
  notify()
}

export function toLine(e: BusEvent): FeedLine {
  const t = Date.parse(e.ts) // naive ISO = local time, which is what the server wrote
  return {
    id: `be-${e.seq}`,
    origin: 'back',
    seq: e.seq,
    t: Number.isFinite(t) ? t : Date.now(),
    ts: e.ts,
    level: e.level,
    source: e.source,
    msg: e.msg,
    data: e.data,
  }
}

function push(events: BusEvent[]) {
  const fresh = events.filter((e) => e.seq > lastSeq)
  if (!fresh.length) return
  lastSeq = fresh[fresh.length - 1].seq
  const next = lines.concat(fresh.map(toLine))
  lines = next.length > CAPACITY ? next.slice(next.length - CAPACITY) : next
  notify()
}

function gap(count: number) {
  if (count <= 0) return
  const now = Date.now()
  lines = lines.concat({
    id: `gap-${now}`,
    origin: 'front',
    t: now,
    ts: new Date(now).toISOString(),
    level: 'warning',
    source: 'stream',
    msg: `${count} backend events were dropped from the server buffer before they could be delivered`,
  })
  notify()
}

function authToken(): string {
  try {
    return localStorage.getItem('netscan_token') ?? ''
  } catch {
    return ''
  }
}

async function pollOnce() {
  try {
    const token = authToken()
    const resp = await fetch(`${BASE}/api/events?since=${lastSeq}&limit=1000`, {
      headers: token ? { 'X-API-Key': token } : {},
    })
    if (!resp.ok) {
      setState('offline')
      return
    }
    const body = (await resp.json()) as { events: BusEvent[]; dropped: number }
    gap(body.dropped)
    push(body.events)
    if (state !== 'live') setState('polling')
  } catch {
    setState('offline')
  }
}

function startPolling() {
  if (pollTimer) return
  pollOnce()
  pollTimer = setInterval(pollOnce, 2000)
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = undefined
}

function connect() {
  if (refs === 0) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const host = BASE ? new URL(BASE).host : location.host
  const token = authToken()
  const qs = new URLSearchParams({ since: String(lastSeq) })
  if (token) qs.set('token', token)
  let socket: WebSocket
  try {
    socket = new WebSocket(`${proto}://${host}/ws/events?${qs}`)
  } catch {
    startPolling()
    scheduleReconnect()
    return
  }
  ws = socket
  socket.onopen = () => {
    backoff = 1000
    stopPolling()
    setState('live')
    logFront('ws', `event stream connected (${proto}://${host}/ws/events, resuming after seq ${lastSeq})`)
  }
  socket.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data)
      if (data && data.type === 'hello') {
        gap(data.dropped ?? 0)
        return
      }
      push([data as BusEvent])
    } catch {
      /* malformed frame — ignore */
    }
  }
  socket.onclose = (ev) => {
    if (ws !== socket) return
    ws = null
    if (refs === 0) return
    logFront(
      'ws',
      `event stream closed (code ${ev.code}${ev.code === 4401 ? ' — bad token' : ''}); polling /api/events, retrying in ${Math.round(backoff / 1000)} s`,
      'warning',
    )
    setState('polling')
    startPolling()
    scheduleReconnect()
  }
}

function scheduleReconnect() {
  clearTimeout(retryTimer)
  retryTimer = setTimeout(connect, backoff)
  backoff = Math.min(backoff * 2, 15000)
}

/** Reference-counted: the socket lives while at least one consumer holds it. */
export function acquireEventStream(): () => void {
  refs += 1
  if (refs === 1) {
    setState('connecting')
    connect()
  }
  return () => {
    refs = Math.max(0, refs - 1)
    if (refs === 0) {
      clearTimeout(retryTimer)
      stopPolling()
      const s = ws
      ws = null
      s?.close()
    }
  }
}

export function subscribeBack(l: () => void): () => void {
  listeners.add(l)
  return () => listeners.delete(l)
}

export const backLines = () => lines
export const streamState = () => state
export const lastBackSeq = () => lastSeq

export function clearBack() {
  lines = []
  notify()
}
