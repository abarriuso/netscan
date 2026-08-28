import { useCallback, useEffect, useRef, useState } from 'react'
import { api, progressSocket } from '@/lib/api'
import type { ScanProgress, ScanStage } from '@/types'

/** Poll an API getter on an interval; refreshKey forces an extra fetch. */
export function usePoll<T>(getter: () => Promise<T>, intervalMs = 10000, refreshKey = 0) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Keep the latest getter in a ref: inline lambdas change identity every
  // render and would otherwise reset the interval on each render.
  const getterRef = useRef(getter)
  useEffect(() => {
    getterRef.current = getter
  })

  const refresh = useCallback(() => {
    getterRef
      .current()
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

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
    let dead = false
    let retry: ReturnType<typeof setTimeout> | undefined
    const connect = () => {
      if (dead) return
      const ws = progressSocket((p) => {
        setProgress(p)
        if (p.stage === 'done' || p.stage.startsWith('error')) setScanning(false)
        else if (p.stage !== 'idle') setScanning(true)
      })
      ws.onclose = () => {
        if (!dead) retry = setTimeout(connect, 3000)
      }
      wsRef.current = ws
    }
    connect()
    return () => {
      dead = true
      if (retry) clearTimeout(retry)
      const ws = wsRef.current
      wsRef.current = null
      if (ws) {
        ws.onclose = null // no reconnect after unmount
        ws.close()
      }
    }
  }, [])

  const startScan = useCallback(async (opts: { full?: boolean; only?: ScanStage } = {}) => {
    setScanning(true)
    try {
      await api.startScan(opts)
    } catch {
      setScanning(false)
    }
  }, [])

  return { progress, scanning, startScan }
}

/** Smoothly animate a numeric value toward its target with requestAnimationFrame. */
export function useAnimatedNumber(target: number, duration = 600): number {
  const [value, setValue] = useState(target)
  const fromRef = useRef(target)
  const rafRef = useRef<number>(0)

  // Track the latest displayed value in an effect (never during render) so the
  // next animation can start from wherever we currently are.
  const valueRef = useRef(target)
  useEffect(() => {
    valueRef.current = value
  }, [value])

  useEffect(() => {
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduce || !Number.isFinite(target)) {
      // Jump straight to the value on the next frame (no in-effect setState).
      rafRef.current = requestAnimationFrame(() => setValue(target))
      return () => cancelAnimationFrame(rafRef.current)
    }
    fromRef.current = valueRef.current
    let start = 0
    const tick = (ts: number) => {
      if (!start) start = ts
      const t = Math.min((ts - start) / duration, 1)
      const eased = 1 - Math.pow(1 - t, 3) // easeOutCubic
      setValue(fromRef.current + (target - fromRef.current) * eased)
      if (t < 1) rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [target, duration])

  return value
}

export function formatBps(bytesPerSec?: number): string {
  if (!bytesPerSec || bytesPerSec < 1) return '0 bps'
  const bits = bytesPerSec * 8
  const units = ['bps', 'Kbps', 'Mbps', 'Gbps']
  let value = bits
  let unit = 0
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000
    unit++
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`
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
