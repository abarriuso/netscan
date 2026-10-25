import { useMemo, useState } from 'react'
import { ArrowDownUp } from 'lucide-react'
import { GlassPanel } from '@/components/metrics'
import UptimeBar from '@/components/UptimeBar'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import { openDeviceDetail } from '@/lib/deviceDetail'
import { availabilityTone, fmtAgo, fmtAvailability, fmtDuration, fmtMs, rttTone } from '@/lib/format'
import type { UptimeDevice } from '@/types'
import PanelError from './PanelError'
import { useI18n } from '@/i18n/context'

const WINDOWS = [
  { key: '1h', hours: 1, slots: 12 },
  { key: '24h', hours: 24, slots: 48 },
  { key: '7d', hours: 168, slots: 84 },
  { key: '30d', hours: 720, slots: 90 },
] as const
type WindowKey = (typeof WINDOWS)[number]['key']

const TONE_TEXT = { ok: 'text-ok', warn: 'text-warn', bad: 'text-destructive', none: 'text-muted-foreground' }

type SortKey = 'availability' | 'name' | 'outages' | 'rtt'

/** Per-device availability over 1 h / 24 h / 7 d / 30 d from the live
 *  monitor's probes: status bars, availability %, coverage, outages, MTTR. */
export default function UptimeBoard() {
  const { t, locale } = useI18n()
  const [win, setWin] = useState<WindowKey>('24h')
  const [filter, setFilter] = useState<'all' | 'down' | 'degraded'>('all')
  const [sort, setSort] = useState<SortKey>('availability')
  const cfg = WINDOWS.find((w) => w.key === win)!
  const { data, error, refresh } = usePoll(() => api.uptime(cfg.hours, cfg.slots), 30000, cfg.hours)

  const rows = useMemo(() => {
    const list = (data?.devices ?? []).filter((d) => {
      const a = d.windows[win].availability_pct
      if (filter === 'down') return !d.online
      if (filter === 'degraded') return a != null && a < 99
      return true
    })
    const byAvail = (d: UptimeDevice) => d.windows[win].availability_pct ?? 101
    return [...list].sort((a, b) => {
      if (sort === 'name') return a.name.localeCompare(b.name)
      if (sort === 'outages') return b.outages_30d - a.outages_30d
      if (sort === 'rtt') return (b.latency_ms ?? -1) - (a.latency_ms ?? -1)
      return byAvail(a) - byAvail(b)
    })
  }, [data, win, filter, sort])

  const summary = useMemo(() => {
    const devs = data?.devices ?? []
    const avail = devs.map((d) => d.windows[win].availability_pct).filter((v): v is number => v != null)
    const cov = devs.map((d) => d.windows[win].coverage_pct).filter((v): v is number => v != null)
    return {
      up: devs.filter((d) => d.online).length,
      total: devs.length,
      fleet: avail.length ? avail.reduce((a, b) => a + b, 0) / avail.length : null,
      coverage: cov.length ? Math.max(...cov) : null,
      outages24: devs.reduce((n, d) => n + d.outages_24h, 0),
    }
  }, [data, win])

  const chip = (active: boolean) =>
    `rounded-none border px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-wider transition-colors ${active ? 'border-primary/60 bg-primary/[0.12] text-primary' : 'border-border text-muted-foreground hover:text-foreground'}`

  return (
    <GlassPanel
      title={t('uptimeTitle')}
      right={
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          {WINDOWS.map((w) => (
            <button key={w.key} className={chip(win === w.key)} onClick={() => setWin(w.key)}>
              {w.key}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-border" />
          {(['all', 'down', 'degraded'] as const).map((f) => (
            <button key={f} className={chip(filter === f)} onClick={() => setFilter(f)}>
              {t(f === 'all' ? 'uptimeAll' : f === 'down' ? 'uptimeDown' : 'uptimeDegraded')}
            </button>
          ))}
        </div>
      }
    >
      <PanelError error={error} onRetry={refresh} />

      <div className="mb-4 grid grid-cols-2 gap-3 font-mono text-xs sm:grid-cols-5">
        <Stat label={t('uptimeUpNow')} value={`${summary.up} / ${summary.total}`} />
        <Stat
          label={t('uptimeFleet', win)}
          value={fmtAvailability(summary.fleet)}
          cls={TONE_TEXT[availabilityTone(summary.fleet)]}
          hint={t('uptimeFleetHint')}
        />
        <Stat label={t('uptimeCoverage')} value={summary.coverage != null ? `${summary.coverage.toFixed(1)} %` : '—'} hint={t('uptimeCoverageHint')} />
        <Stat label={t('uptimeOutages24')} value={String(summary.outages24)} cls={summary.outages24 ? 'text-warn' : 'text-ok'} />
        <Stat label={t('uptimeProbe')} value={data ? `${data.interval_s} s · ${t('uptimeSlot', fmtDuration(data.slot_s))}` : '—'} />
      </div>

      {data && data.devices.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">{t('mapEmpty')}</p>}

      {rows.length > 0 && (
        <div className="-mx-1 overflow-x-auto">
          <table className="w-full min-w-[860px] border-separate border-spacing-y-1 px-1 text-xs">
            <thead>
              <tr className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-muted-foreground">
                <th className="text-left font-medium">
                  <SortBtn active={sort === 'name'} onClick={() => setSort('name')}>{t('uptimeDevice')}</SortBtn>
                </th>
                <th className="text-right font-medium">
                  <SortBtn active={sort === 'rtt'} onClick={() => setSort('rtt')}>RTT</SortBtn>
                </th>
                <th className="text-right font-medium">{t('uptimeState')}</th>
                <th className="text-right font-medium">
                  <SortBtn active={sort === 'availability'} onClick={() => setSort('availability')}>{t('uptimeAvail')}</SortBtn>
                </th>
                <th className="w-[38%] pl-3 text-left font-medium">{t('uptimeTimeline', win)}</th>
                <th className="text-right font-medium">
                  <SortBtn active={sort === 'outages'} onClick={() => setSort('outages')}>{t('uptimeOutages')}</SortBtn>
                </th>
                <th className="text-right font-medium">MTTR</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => {
                const w = d.windows[win]
                return (
                  <tr key={d.mac} className="bg-white/[0.02] hover:bg-white/[0.045]">
                    <td className="py-1.5 pl-2">
                      <button onClick={() => openDeviceDetail(d.mac)} className="flex items-center gap-2 text-left hover:text-primary">
                        <span
                          className={`h-2 w-2 shrink-0 ${d.online ? 'bg-ok' : 'bg-destructive'}`}
                          style={{ boxShadow: d.online ? '0 0 6px #36e09e' : '0 0 6px #ff4a5e' }}
                        />
                        <span className="min-w-0">
                          <span className="block max-w-[180px] truncate font-semibold">{d.name}</span>
                          {d.name !== d.ip && <span className="block font-mono text-[10.5px] text-muted-foreground">{d.ip}</span>}
                        </span>
                      </button>
                    </td>
                    <td className="text-right font-mono">
                      <span className={TONE_TEXT[rttTone(d.latency_ms)]}>{fmtMs(d.latency_ms)}</span>
                      {d.method && <span className="ml-1.5 border border-border px-1 text-[9.5px] text-muted-foreground">{d.method}</span>}
                    </td>
                    <td
                      className="text-right font-mono text-[11px] text-muted-foreground"
                      title={d.state_since_exact ? (d.state_since ?? '') : t('uptimeSinceHint')}
                    >
                      {d.online ? t('uptimeUpFor') : t('uptimeDownFor')}{' '}
                      {d.state_since ? `${d.state_since_exact ? '' : '≥ '}${fmtAgo(d.state_since)}` : '—'}
                    </td>
                    <td className="text-right font-mono">
                      <span className={`font-semibold ${TONE_TEXT[availabilityTone(w.availability_pct)]}`}>
                        {fmtAvailability(w.availability_pct)}
                      </span>
                      <span className="block text-[10px] text-muted-foreground" title={t('uptimeCoverageHint')}>
                        {w.coverage_pct != null ? t('uptimeCov', w.coverage_pct.toFixed(1)) : ''}
                      </span>
                    </td>
                    <td className="pl-3">
                      <UptimeBar slots={d.timeline} slotS={data!.slot_s} locale={locale} noDataLabel={t('uptimeNoData')} />
                    </td>
                    <td className="text-right font-mono">
                      <span className={d.outages_24h ? 'text-warn' : 'text-muted-foreground'}>{d.outages_24h}</span>
                      <span className="text-muted-foreground"> / {d.outages_30d}</span>
                    </td>
                    <td className="pr-2 text-right font-mono text-muted-foreground">{fmtDuration(d.mttr_s)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 font-mono text-[10.5px] leading-relaxed text-muted-foreground">{t('uptimeLegend')}</p>
    </GlassPanel>
  )
}

function Stat({ label, value, cls = '', hint }: { label: string; value: string; cls?: string; hint?: string }) {
  return (
    <div className="border border-border/70 bg-white/[0.02] px-3 py-2" title={hint}>
      <span className="block text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className={`text-[15px] font-bold tabular-nums ${cls}`}>{value}</span>
    </div>
  )
}

function SortBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className={`inline-flex items-center gap-1 hover:text-foreground ${active ? 'text-primary' : ''}`}>
      {children}
      <ArrowDownUp className="h-3 w-3 opacity-60" />
    </button>
  )
}
