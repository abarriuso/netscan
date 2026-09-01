import { AnimatedNumber } from '@/components/metrics'
import { Skeleton } from '@/components/ui/skeleton'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import PanelError from './PanelError'

function Kpi({
  label,
  value,
  frac,
  delta,
  tone,
  accent,
}: {
  label: string
  value: React.ReactNode
  frac?: string
  delta?: React.ReactNode
  tone?: 'good' | 'warn' | 'bad'
  /** Renders `value` with the violet→teal gradient text treatment. */
  accent?: boolean
}) {
  const deltaClass = tone === 'good' ? 'text-ok' : tone === 'warn' ? 'text-warn' : tone === 'bad' ? 'text-destructive' : ''
  // Only gradient-fill when there's a real number — clipping a lone "—"
  // placeholder through `color: transparent` just makes it disappear.
  const showAccent = accent && value !== '—'
  return (
    <div className="glass card-hover flex flex-col gap-1.5 px-[18px] py-4">
      <span className="text-[11.5px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
      <span
        className={`text-[26px] font-extrabold leading-none tracking-tight transition-colors duration-300 ${showAccent ? 'text-gradient' : ''}`}
      >
        {value}
        {frac && (
          <span
            className="text-base font-semibold text-muted-foreground"
            style={showAccent ? { WebkitTextFillColor: 'currentColor' } : undefined}
          >
            {frac}
          </span>
        )}
      </span>
      {delta && <span className={`text-[11.5px] font-semibold transition-colors duration-300 ${deltaClass}`}>{delta}</span>}
    </div>
  )
}

export default function StatCards({ refreshKey }: { refreshKey: number }) {
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

  return (
    <div className="space-y-2">
      <PanelError error={error} />
      <div className="grid grid-cols-2 gap-[14px] lg:grid-cols-3 xl:grid-cols-6">
        <Kpi
          label="dispositivos online"
          value={<AnimatedNumber value={data?.devices_online ?? 0} />}
          frac={` / ${data?.devices_total ?? 0}`}
          delta="desde el último scan"
        />
        <Kpi
          label="sin verificar"
          value={<AnimatedNumber value={data?.devices_untrusted ?? 0} />}
          delta={(data?.devices_untrusted ?? 0) > 0 ? 'revisar' : 'todo ok'}
          tone={(data?.devices_untrusted ?? 0) > 0 ? 'warn' : 'good'}
        />
        <Kpi
          label="alertas sin leer"
          value={<AnimatedNumber value={data?.alerts_unacknowledged ?? 0} />}
          delta={(data?.alerts_unacknowledged ?? 0) > 0 ? 'acción requerida' : 'todo tranquilo'}
          tone={(data?.alerts_unacknowledged ?? 0) > 0 ? 'bad' : 'good'}
        />
        <Kpi
          label="calidad media"
          value={m?.avg_quality != null ? <AnimatedNumber value={m.avg_quality} /> : '—'}
          frac={m?.avg_quality != null ? '/100' : undefined}
          delta="estable"
          tone="good"
          accent
        />
        <Kpi
          label="latencia media"
          value={m?.avg_latency_ms != null ? <AnimatedNumber value={m.avg_latency_ms} decimals={1} /> : '—'}
          frac={m?.avg_latency_ms != null ? ' ms' : undefined}
        />
        <Kpi
          label="throughput máx"
          value={m?.max_throughput_mbps != null ? <AnimatedNumber value={m.max_throughput_mbps} decimals={0} /> : '—'}
          frac={m?.max_throughput_mbps != null ? ' Mbps' : undefined}
        />
      </div>
    </div>
  )
}
