import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
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
    // Pause polling while the tab is hidden — background tabs shouldn't keep
    // hammering the API — and catch up immediately on becoming visible again.
    const id = setInterval(() => {
      if (!document.hidden) refresh()
    }, intervalMs)
    const onVisible = () => {
      if (!document.hidden) refresh()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [refresh, intervalMs, refreshKey])

  return { data, error, refresh }
}

/** Live scan progress: WebSocket for low latency, plus an HTTP fallback poll
 *  while a scan runs so the UI keeps updating even if the socket never connects
 *  (a reverse proxy without WS upgrade, say) — a running scan must never look
 *  frozen. Also exposes elapsed seconds and fires start/failure toasts. */
export function useScanProgress() {
  const [progress, setProgress] = useState<ScanProgress>({ stage: 'idle', done: 0, total: 0 })
  const [scanning, setScanning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const wsRef = useRef<WebSocket | null>(null)
  const startRef = useRef<number>(0)

  const apply = useCallback((p: ScanProgress) => {
    setProgress(p)
    if (p.stage === 'done' || p.stage.startsWith('error')) setScanning(false)
    else if (p.stage !== 'idle') setScanning(true)
  }, [])

  useEffect(() => {
    let dead = false
    let retry: ReturnType<typeof setTimeout> | undefined
    const connect = () => {
      if (dead) return
      const ws = progressSocket((p) => apply(p as ScanProgress))
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
  }, [apply])

  // HTTP fallback while scanning.
  useEffect(() => {
    if (!scanning) return
    const id = setInterval(() => {
      api
        .scanProgress()
        .then((p) => apply(p as ScanProgress))
        .catch(() => {})
    }, 2000)
    return () => clearInterval(id)
  }, [scanning, apply])

  // Elapsed-time ticker (real progress feedback, not decoration).
  useEffect(() => {
    if (!scanning) return
    if (!startRef.current) startRef.current = Date.now()
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000)
    return () => clearInterval(id)
  }, [scanning])

  const startScan = useCallback(async (opts: { full?: boolean; only?: ScanStage } = {}) => {
    startRef.current = Date.now()
    setElapsed(0)
    setScanning(true)
    setProgress({ stage: opts.only ?? 'arp', done: 0, total: 0 })
    toast(
      opts.full ? 'Escaneo completo iniciado' : opts.only ? `Ejecutando: ${opts.only}` : 'Escaneo rápido iniciado',
      { description: 'Puedes seguir el progreso en la cabecera.' },
    )
    try {
      await api.startScan(opts)
    } catch (e) {
      setScanning(false)
      toast.error('No se pudo iniciar el escaneo', { description: (e as Error).message })
    }
  }, [])

  return { progress, scanning, elapsed, startScan }
}

/** Smoothly animate a numeric value toward its target with requestAnimationFrame
 *  (easeOutCubic). Respects prefers-reduced-motion. */
export function useAnimatedNumber(target: number, duration = 700): number {
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
