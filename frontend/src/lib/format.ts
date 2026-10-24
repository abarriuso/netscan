// Unit formatting — one place, one convention for the whole dashboard.
//
//   time        → ms with precision by magnitude (LAN RTTs are sub-millisecond)
//   durations   → s / min / h / d, two most significant units
//   data sizes  → IEC binary prefixes (KiB, MiB, GiB: powers of 1024)
//   data rates  → SI decimal bits per second (kbit/s, Mbit/s: powers of 1000)
//   ratios      → percent with an explicit "%" and fixed decimals
//
// Every formatter returns "—" for null/undefined/NaN so missing data never
// renders as "0" (which would be a lie).

export const DASH = '—'

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)

/** Milliseconds: 0.42 ms · 3.7 ms · 125 ms · 2.35 s */
export function fmtMs(ms: number | null | undefined): string {
  if (!isNum(ms)) return DASH
  if (ms < 1) return `${ms.toFixed(2)} ms`
  if (ms < 100) return `${ms.toFixed(1)} ms`
  if (ms < 10_000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

/** Seconds as a compact duration: 42 s · 3 min 12 s · 5 h 03 min · 2 d 4 h */
export function fmtDuration(seconds: number | null | undefined): string {
  if (!isNum(seconds)) return DASH
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s} s`
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (d > 0) return `${d} d ${h} h`
  if (h > 0) return `${h} h ${String(m).padStart(2, '0')} min`
  return `${m} min ${s % 60} s`
}

/** Bytes with IEC prefixes: 512 B · 3.4 KiB · 12.0 MiB */
export function fmtBytes(bytes: number | null | undefined): string {
  if (!isNum(bytes)) return DASH
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB']
  let v = bytes
  let i = 0
  while (Math.abs(v) >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return i === 0 ? `${Math.round(v)} B` : `${v.toFixed(v < 10 ? 2 : 1)} ${units[i]}`
}

/** A rate given in BYTES per second, shown in bits per second (SI). */
export function fmtByteRate(bytesPerSec: number | null | undefined): string {
  if (!isNum(bytesPerSec)) return DASH
  return fmtBitRate(bytesPerSec * 8)
}

/** Bits per second (SI): 850 bit/s · 12.4 kbit/s · 940 Mbit/s · 2.50 Gbit/s */
export function fmtBitRate(bitsPerSec: number | null | undefined): string {
  if (!isNum(bitsPerSec)) return DASH
  const units = ['bit/s', 'kbit/s', 'Mbit/s', 'Gbit/s', 'Tbit/s']
  let v = bitsPerSec
  let i = 0
  while (Math.abs(v) >= 1000 && i < units.length - 1) {
    v /= 1000
    i++
  }
  return `${v.toFixed(i === 0 ? 0 : v < 10 ? 2 : v < 100 ? 1 : 0)} ${units[i]}`
}

/** Mbit/s values coming from the API (already in 10^6 bit/s). */
export function fmtMbps(mbps: number | null | undefined): string {
  return isNum(mbps) ? fmtBitRate(mbps * 1_000_000) : DASH
}

/** Percent with fixed decimals: 99.982 % */
export function fmtPct(pct: number | null | undefined, decimals = 1): string {
  return isNum(pct) ? `${pct.toFixed(decimals)} %` : DASH
}

/** Availability percent: more decimals near 100 %, where they matter (99.9 vs 99.99). */
export function fmtAvailability(pct: number | null | undefined): string {
  if (!isNum(pct)) return DASH
  if (pct >= 99.995) return '100 %'
  if (pct >= 99) return `${pct.toFixed(2)} %`
  return `${pct.toFixed(1)} %`
}

/** "12 s ago" / "3 min ago" relative to now (en/es aware through the caller's suffix). */
export function fmtAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return DASH
  const t = new Date(iso).getTime()
  if (!Number.isFinite(t)) return DASH
  return fmtDuration((now - t) / 1000)
}

/** Local wall-clock time, with the date when it is not today. */
export function fmtDateTime(iso: string | null | undefined, locale?: string): string {
  if (!iso) return DASH
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return DASH
  const today = new Date()
  const sameDay = d.toDateString() === today.toDateString()
  return sameDay
    ? d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : d.toLocaleString(locale, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

/** HH:MM:SS.mmm for log lines. */
export function fmtClockMs(epochMs: number): string {
  const d = new Date(epochMs)
  const p = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`
}

/** Colour class for an availability percentage (SLA-style thresholds). */
export function availabilityTone(pct: number | null | undefined): 'ok' | 'warn' | 'bad' | 'none' {
  if (!isNum(pct)) return 'none'
  if (pct >= 99) return 'ok'
  if (pct >= 95) return 'warn'
  return 'bad'
}

/** Colour class for a round-trip time on a LAN. */
export function rttTone(ms: number | null | undefined): 'ok' | 'warn' | 'bad' | 'none' {
  if (!isNum(ms)) return 'none'
  if (ms < 5) return 'ok'
  if (ms < 30) return 'warn'
  return 'bad'
}
