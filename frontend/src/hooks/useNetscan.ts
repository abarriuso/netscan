import { useCallback, useEffect, useRef, useState } from 'react'
import { api, progressSocket } from '@/lib/api'
import type { ScanProgress } from '@/types'

/** Poll an API getter on an interval; refreshKey forces an extra fetch. */
export function usePoll<T>(getter: () => Promise<T>, intervalMs = 10000, refreshKey = 0) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    getter()
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
  }, [getter])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, intervalMs)
    return () => clearInterval(id)
  }, [refresh, intervalMs, refreshKey])

  return { data, error, refresh }
}

/** Live scan progress over WebSocket with a one-shot HTTP fallback. */
export function useScanProgress() {
  const [progress, setProgress] = useState<ScanProgress>({ stage: 'idle', done: 0, total: 0 })
  const [scanning, setScanning] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const connect = () => {
      const ws = progressSocket((p) => {
        setProgress(p)
        if (p.stage === 'done' || p.stage.startsWith('error')) setScanning(false)
        else if (p.stage !== 'idle') setScanning(true)
      })
      ws.onclose = () => setTimeout(connect, 3000)
      wsRef.current = ws
    }
    connect()
    return () => wsRef.current?.close()
  }, [])

  const startScan = useCallback(async (full: boolean) => {
    setScanning(true)
    try {
      await api.startScan(full)
    } catch {
      setScanning(false)
    }
  }, [])

  return { progress, scanning, startScan }
}

export function formatBytes(bytes?: number): string {
  if (!bytes) return '—'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit++
  }
  return `${value.toFixed(1)} ${units[unit]}`
}

export function formatUptime(seconds?: number): string {
  if (!seconds) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  return d > 0 ? `${d}d ${h}h` : `${h}h ${Math.floor((seconds % 3600) / 60)}m`
}
