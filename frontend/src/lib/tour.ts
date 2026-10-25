// First-run guided tour: open/close state shared by Home (which mounts the
// lazy <Tour/>) and the header "?" button that replays it.
import { useSyncExternalStore } from 'react'
import { logFront } from './telemetry'

export const TOUR_KEY = 'netscan_tour_v1'

let open = false
const listeners = new Set<() => void>()

function set(next: boolean) {
  open = next
  listeners.forEach((l) => l())
}

export function tourSeen(): boolean {
  try {
    return localStorage.getItem(TOUR_KEY) != null
  } catch {
    return true // storage disabled: never nag on every load
  }
}

export function startTour() {
  logFront('ui', 'tutorial started')
  set(true)
}

/** Close the tour and remember how it ended ("done" or "skipped"). */
export function endTour(outcome: 'done' | 'skipped', step?: number) {
  try {
    localStorage.setItem(TOUR_KEY, outcome)
  } catch {
    /* storage disabled — the tour may show again next time */
  }
  logFront('ui', `tutorial ${outcome}${step != null ? ` at step ${step + 1}` : ''}`)
  set(false)
}

function subscribe(l: () => void) {
  listeners.add(l)
  return () => listeners.delete(l)
}

export function useTourOpen(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => open,
    () => open,
  )
}
