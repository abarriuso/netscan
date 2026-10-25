// Frontend-side event log: every API call the dashboard makes, WebSocket
// state changes, user actions and client errors. Shown next to the backend
// events in the terminal dock, so "what is the UI doing" is never a mystery.
import type { FeedLevel, FeedLine } from '@/types'

const CAPACITY = 2000

type Listener = () => void

let lines: FeedLine[] = []
let counter = 0
const listeners = new Set<Listener>()
let notifyScheduled = false

function notify() {
  // Coalesce bursts (a dozen polls resolving in the same tick) into one render.
  if (notifyScheduled) return
  notifyScheduled = true
  queueMicrotask(() => {
    notifyScheduled = false
    listeners.forEach((l) => l())
  })
}

export function logFront(source: string, msg: string, level: FeedLevel = 'info', data?: Record<string, unknown>) {
  const now = Date.now()
  counter += 1
  const line: FeedLine = {
    id: `fe-${counter}`,
    origin: 'front',
    t: now,
    ts: new Date(now).toISOString(),
    level,
    source,
    msg,
    data,
  }
  lines = lines.length >= CAPACITY ? [...lines.slice(lines.length - CAPACITY + 1), line] : [...lines, line]
  notify()
}

export function frontLines(): FeedLine[] {
  return lines
}

export function subscribeFront(l: Listener): () => void {
  listeners.add(l)
  return () => listeners.delete(l)
}

export function clearFront() {
  lines = []
  notify()
}

// Uncaught errors are part of the picture too.
if (typeof window !== 'undefined') {
  window.addEventListener('error', (e) => logFront('ui', `uncaught error: ${e.message}`, 'error'))
  window.addEventListener('unhandledrejection', (e) =>
    logFront('ui', `unhandled promise rejection: ${String((e.reason as Error)?.message ?? e.reason)}`, 'error'),
  )
}
