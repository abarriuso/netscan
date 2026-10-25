// App-wide "open the detail of device X" channel, so the table, the uptime
// board, the network map and the security ranking all open the same dialog
// (rendered once, by <DeviceDetailHost/> in Home).
import { useSyncExternalStore } from 'react'
import { logFront } from './telemetry'

let current: string | null = null
const listeners = new Set<() => void>()

export function openDeviceDetail(mac: string) {
  current = mac
  logFront('ui', `opened device detail ${mac}`, 'debug')
  listeners.forEach((l) => l())
}

export function closeDeviceDetail() {
  current = null
  listeners.forEach((l) => l())
}

function subscribe(l: () => void) {
  listeners.add(l)
  return () => listeners.delete(l)
}

export function useDeviceDetailTarget(): string | null {
  return useSyncExternalStore(
    subscribe,
    () => current,
    () => current,
  )
}
