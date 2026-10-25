import { fmtAvailability, fmtMs } from '@/lib/format'
import type { UptimeSlot } from '@/types'

function slotClass(pct: number | null): string {
  if (pct == null) return 'bg-white/[0.06]'
  if (pct >= 99.5) return 'bg-ok/80'
  if (pct >= 95) return 'bg-[#a3e635]/70'
  if (pct >= 80) return 'bg-warn/80'
  return 'bg-destructive/85'
}

function fmtRange(startIso: string, slotS: number, locale?: string): string {
  const start = new Date(startIso)
  const end = new Date(start.getTime() + slotS * 1000)
  const sameDay = start.toDateString() === new Date().toDateString()
  const opt: Intl.DateTimeFormatOptions = sameDay
    ? { hour: '2-digit', minute: '2-digit' }
    : { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }
  return `${start.toLocaleString(locale, opt)} – ${end.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}`
}

/** Status-page style availability bars: one bar per time slot, coloured by
 *  the share of live probes answered in it (grey = NetScan was not running /
 *  no probe in that slot — "no data", never "down"). */
export default function UptimeBar({
  slots,
  slotS,
  height = 22,
  locale,
  noDataLabel = 'no data',
}: {
  slots: UptimeSlot[]
  slotS: number
  height?: number
  locale?: string
  noDataLabel?: string
}) {
  return (
    <div className="flex w-full items-stretch gap-[2px]" style={{ height }} role="img" aria-label="availability timeline">
      {slots.map((s) => (
        <div
          key={s.start}
          className={`min-w-[2px] flex-1 ${slotClass(s.availability_pct)} transition-colors hover:brightness-125`}
          title={
            `${fmtRange(s.start, slotS, locale)}\n` +
            (s.availability_pct == null
              ? noDataLabel
              : `${fmtAvailability(s.availability_pct)} · ${s.probes} probes\n` +
                `RTT avg ${fmtMs(s.rtt_avg_ms)} · min ${fmtMs(s.rtt_min_ms)} · max ${fmtMs(s.rtt_max_ms)}`)
          }
        />
      ))}
    </div>
  )
}
