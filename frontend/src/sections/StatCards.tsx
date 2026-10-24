import { AnimatedNumber } from '@/components/metrics'
import { Skeleton } from '@/components/ui/skeleton'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import { fmtAgo, fmtDuration, fmtMs } from '@/lib/format'
import PanelError from './PanelError'
import { useI18n } from '@/i18n/context'

function Kpi({
  label,
  value,
  frac,
  delta,
  tone,
  accent,
  title,
}: {
  label: string
  value: React.ReactNode
  frac?: string
  delta?: React.ReactNode
  tone?: 'good' | 'warn' | 'bad'
  /** Renders `value` with the violet→teal gradient text treatment. */
  accent?: boolean
  title?: string
}) {
  const deltaClass = tone === 'good' ? 'text-ok' : tone === 'warn' ? 'text-warn' : tone === 'bad' ? 'text-destructive' : ''
  // Only gradient-fill when there's a real number — clipping a lone "—"
  // placeholder through `color: transparent` just makes it disappear.
  const showAccent = accent && value !== '—'
  return (
    <div className="glass card-hover group relative flex flex-col gap-1.5 px-[18px] py-4" title={title}>
      <span className="kbd-label flex items-center gap-1.5">
        <span className="text-primary/60">//</span>
        {label}
      </span>
      <span
        className={`font-display text-[27px] font-extrabold leading-none tracking-tight transition-colors duration-300 ${showAccent ? 'text-gradient' : ''}`}
      >
        {value}
        {frac && (
          <span
            className="font-mono text-base font-semibold text-muted-foreground"
            style={showAccent ? { WebkitTextFillColor: 'currentColor' } : undefined}
          >
            {frac}
          </span>
        )}
      </span>
      {delta && <span className={`font-mono text-[10.5px] font-semibold uppercase tracking-wide transition-colors duration-300 ${deltaClass || 'text-muted-foreground'}`}>{delta}</span>}
    </div>
  )
}

/** Overview KPIs. Every sub-line is a real figure (no decorative "stable"). */
export default function StatCards({ refreshKey }: { refreshKey: number }) {
  const { t } = useI18n()
  const { data, error } = usePoll(api.overview, 15000, refreshKey)
  const m = data?.metrics

  if (!data && !error) {
    return (
      <div className="grid grid-cols-2 gap-[14px] lg:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="glass flex flex-col gap-2 px-[18px] py-4">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-7 w-16" />
            <Skeleton className="h-3 w-24" />
          </div>
        ))}
      </div>
    )
  }

  const newDevices = data?.devices_new_24h ?? 0
  const worst = m?.worst_quality

  return (
    <div className="space-y-2">
      <PanelError error={error} />
      {data?.last_scan_error && (
        <p className="border border-destructive/40 bg-destructive/10 px-3 py-2 font-mono text-xs text-destructive">
          {t('lastScanFailed', data.last_scan_error)}
        </p>
      )}
      <div className="grid grid-cols-2 gap-[14px] lg:grid-cols-3 xl:grid-cols-6">
        <Kpi
          label={t('kpiOnline')}
          value={<AnimatedNumber value={data?.devices_online ?? 0} />}
          frac={` / ${data?.devices_total ?? 0}`}
          delta={newDevices > 0 ? t('kpiNew24h', newDevices) : t('kpiNoNew24h')}
          tone={newDevices > 0 ? 'warn' : undefined}
        />
        <Kpi
          label={t('kpiUntrusted')}
          value={<AnimatedNumber value={data?.devices_untrusted ?? 0} />}
          delta={(data?.devices_untrusted ?? 0) > 0 ? t('review') : t('allOk')}
          tone={(data?.devices_untrusted ?? 0) > 0 ? 'warn' : 'good'}
        />
        <Kpi
          label={t('kpiUnread')}
          value={<AnimatedNumber value={data?.alerts_unacknowledged ?? 0} />}
          delta={(data?.alerts_unacknowledged ?? 0) > 0 ? t('actionNeeded') : t('allQuiet')}
          tone={(data?.alerts_unacknowledged ?? 0) > 0 ? 'bad' : 'good'}
        />
        <Kpi
          label={t('kpiQuality')}
          value={m?.avg_quality != null ? <AnimatedNumber value={m.avg_quality} /> : '—'}
          frac={m?.avg_quality != null ? '/100' : undefined}
          delta={worst != null ? t('kpiWorst', worst, m?.devices_measured ?? 0) : t('noData')}
          tone={worst == null ? undefined : worst >= 80 ? 'good' : worst >= 50 ? 'warn' : 'bad'}
          accent
          title={t('kpiQualityHint')}
        />
        <Kpi
          label={t('kpiLatency')}
          value={m?.avg_latency_ms != null ? fmtMs(m.avg_latency_ms).replace(' ms', '') : '—'}
          frac={m?.avg_latency_ms != null ? ' ms' : undefined}
          delta={m?.p95_latency_ms != null ? `p95 ${fmtMs(m.p95_latency_ms)}` : undefined}
          title={t('kpiLatencyHint')}
        />
        <Kpi
          label={t('kpiLastScan')}
          value={data?.last_scan ? fmtAgo(data.last_scan) : '—'}
          delta={
            data?.last_scan_duration_s != null
              ? `${t('kpiTook', fmtDuration(data.last_scan_duration_s))}${data?.next_scan ? ` · ${t('kpiNext', new Date(data.next_scan).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))}` : ''}`
              : t('noScans')
          }
        />
      </div>
    </div>
  )
}
