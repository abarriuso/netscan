import { Activity, BellRing, Gauge, MonitorCheck, ShieldAlert, Wifi } from 'lucide-react'
import { AnimatedNumber } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import PanelError from './PanelError'

function Stat({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof MonitorCheck
  label: string
  value: React.ReactNode
  /** Only the two genuinely-actionable metrics get a status color; the rest stay neutral. */
  tone?: 'warn' | 'danger'
}) {
  return (
    <div className="flex flex-col gap-2.5 bg-card p-4">
      <Icon
        className={`h-4 w-4 ${tone === 'warn' ? 'text-warn' : tone === 'danger' ? 'text-destructive' : 'text-muted-foreground'}`}
        strokeWidth={1.5}
      />
      <div>
        <div
          className={`font-mono text-[22px] font-semibold leading-none ${tone === 'warn' ? 'text-warn' : tone === 'danger' ? 'text-destructive' : ''}`}
        >
          {value}
        </div>
        <div className="mt-1.5 truncate font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
      </div>
    </div>
  )
}

export default function StatCards({ refreshKey }: { refreshKey: number }) {
  const { data, error } = usePoll(api.overview, 15000, refreshKey)
  const m = data?.metrics

  return (
    <div className="space-y-2">
      <PanelError error={error} />
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border lg:grid-cols-3 xl:grid-cols-6">
        <Stat
          icon={MonitorCheck}
          label="online / total"
          value={
            <span>
              <AnimatedNumber value={data?.devices_online ?? 0} />
              <span className="font-normal text-muted-foreground">
                {' '}
                / <AnimatedNumber value={data?.devices_total ?? 0} />
              </span>
            </span>
          }
        />
        <Stat
          icon={ShieldAlert}
          label="sin verificar"
          value={<AnimatedNumber value={data?.devices_untrusted ?? 0} />}
          tone="warn"
        />
        <Stat
          icon={BellRing}
          label="alertas"
          value={<AnimatedNumber value={data?.alerts_unacknowledged ?? 0} />}
          tone="danger"
        />
        <Stat
          icon={Gauge}
          label="calidad media"
          value={
            m?.avg_quality != null ? (
              <span>
                <AnimatedNumber value={m.avg_quality} />
                <span className="text-sm font-normal text-muted-foreground">/100</span>
              </span>
            ) : (
              '—'
            )
          }
        />
        <Stat
          icon={Activity}
          label="latencia media"
          value={
            m?.avg_latency_ms != null ? (
              <span>
                <AnimatedNumber value={m.avg_latency_ms} decimals={1} />
                <span className="text-sm font-normal text-muted-foreground">ms</span>
              </span>
            ) : (
              '—'
            )
          }
        />
        <Stat
          icon={Wifi}
          label="throughput máx"
          value={
            m?.max_throughput_mbps != null ? (
              <span>
                <AnimatedNumber value={m.max_throughput_mbps} decimals={0} />
                <span className="text-sm font-normal text-muted-foreground">Mbps</span>
              </span>
            ) : (
              '—'
            )
          }
        />
      </div>
    </div>
  )
}
