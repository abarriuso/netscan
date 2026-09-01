import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { GlassPanel } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import PanelError from './PanelError'

function fmtTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

type Row = Record<string, number | string | null>

/** One small-multiple area chart: a single series over time, its own y-axis,
 *  crosshair tooltip, and a soft gradient fill. Colours are literal hexes (not
 *  CSS vars) because Recharts writes them as SVG attributes, where `var(--x)`
 *  does not resolve. */
function TrendChart({
  title,
  unit,
  color,
  gradientId,
  data,
  dataKey,
  decimals = 0,
}: {
  title: string
  unit: string
  color: string
  gradientId: string
  data: Row[]
  dataKey: string
  decimals?: number
}) {
  const present = data.filter((d) => d[dataKey] != null)
  const last = present.length ? (present[present.length - 1][dataKey] as number) : null

  return (
    <GlassPanel title={title} meta={last != null ? `${last.toFixed(decimals)}${unit}` : '—'}>
      {present.length < 2 ? (
        <p className="py-8 text-center text-xs text-muted-foreground">
          datos insuficientes — hacen falta ≥2 escaneos
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={148}>
          <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={color} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis
              dataKey="t"
              tickFormatter={fmtTime}
              tick={{ fill: 'rgba(255,255,255,0.42)', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              minTickGap={40}
            />
            <YAxis
              width={42}
              tick={{ fill: 'rgba(255,255,255,0.42)', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              domain={['auto', 'auto']}
            />
            <Tooltip
              cursor={{ stroke: color, strokeOpacity: 0.4 }}
              contentStyle={{
                background: 'rgba(22,18,31,0.95)',
                border: '1px solid rgba(255,255,255,0.12)',
                borderRadius: 10,
                fontSize: 12,
              }}
              labelStyle={{ color: 'rgba(255,255,255,0.6)' }}
              labelFormatter={(v) => fmtTime(String(v))}
              formatter={(val: number | string) => [`${Number(val).toFixed(decimals)}${unit}`, title]}
            />
            <Area
              type="monotone"
              dataKey={dataKey}
              stroke={color}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0 }}
              connectNulls
              isAnimationActive
              animationDuration={700}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </GlassPanel>
  )
}

/** Time-series trends for the whole network: latency, quality, throughput
 *  (averaged per scan) and devices discovered per scan. */
export default function TrendsPanel({ refreshKey }: { refreshKey: number }) {
  const { data: hist, error } = usePoll(() => api.metricsHistory(200), 30000, refreshKey)
  const { data: scans, error: scanErr } = usePoll(() => api.scanHistory(100), 30000, refreshKey)

  const points: Row[] = (hist?.points ?? []) as unknown as Row[]
  const scanRows: Row[] = (scans?.scans ?? []).map((s) => ({ t: s.started_at, total_devices: s.total_devices }))

  if (points.length === 0 && scanRows.length === 0) {
    return (
      <GlassPanel title="Tendencias en el tiempo">
        <PanelError error={error || scanErr} />
        <p className="text-sm text-muted-foreground">sin histórico todavía — lanza algún scan</p>
      </GlassPanel>
    )
  }

  return (
    <div className="space-y-2">
      <PanelError error={error || scanErr} />
      <div className="grid gap-[18px] md:grid-cols-2 xl:grid-cols-4">
        <TrendChart title="Latencia media" unit=" ms" color="#2dd4bf" gradientId="tr-lat" data={points} dataKey="avg_latency_ms" decimals={1} />
        <TrendChart title="Calidad media" unit="/100" color="#8b5cf6" gradientId="tr-q" data={points} dataKey="avg_quality" />
        <TrendChart title="Throughput medio" unit=" Mbps" color="#3b82f6" gradientId="tr-tp" data={points} dataKey="avg_throughput_mbps" />
        <TrendChart title="Dispositivos por scan" unit="" color="#ec4899" gradientId="tr-dev" data={scanRows} dataKey="total_devices" />
      </div>
    </div>
  )
}
