import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import type { DeviceRecord, MetricSamplePoint } from '@/types'

function fmtT(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function Mini({
  data,
  dataKey,
  color,
  unit,
  title,
  decimals = 0,
}: {
  data: MetricSamplePoint[]
  dataKey: string
  color: string
  unit: string
  title: string
  decimals?: number
}) {
  const rows = data as unknown as Record<string, number | null | string>[]
  const present = rows.filter((d) => d[dataKey] != null)
  const last = present.length ? Number(present[present.length - 1][dataKey]) : null
  const gid = `dd-${dataKey}`
  return (
    <div className="glass p-3">
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-semibold text-muted-foreground">{title}</span>
        <span className="font-mono text-foreground/90">{last != null ? `${last.toFixed(decimals)}${unit}` : '—'}</span>
      </div>
      {present.length < 2 ? (
        <p className="py-6 text-center text-[11px] text-muted-foreground">sin histórico suficiente</p>
      ) : (
        <ResponsiveContainer width="100%" height={110}>
          <AreaChart data={data} margin={{ top: 4, right: 6, bottom: 0, left: -20 }}>
            <defs>
              <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.32} />
                <stop offset="100%" stopColor={color} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis dataKey="t" tickFormatter={fmtT} tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }} tickLine={false} axisLine={false} minTickGap={36} />
            <YAxis width={40} tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }} tickLine={false} axisLine={false} domain={['auto', 'auto']} />
            <Tooltip
              contentStyle={{ background: 'rgba(11,13,17,0.96)', border: '1px solid rgba(45,226,230,0.35)', borderRadius: 2, fontSize: 12, fontFamily: 'JetBrains Mono' }}
              labelStyle={{ color: 'rgba(255,255,255,0.6)' }}
              labelFormatter={(v) => fmtT(String(v))}
              formatter={(val: number | string) => [`${Number(val).toFixed(decimals)}${unit}`, title]}
            />
            <Area type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} fill={`url(#${gid})`} dot={false} connectNulls isAnimationActive animationDuration={500} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

/** Per-device history: latency / quality / jitter / packet-loss over time,
 *  from the metric samples persisted on every scan. */
export default function DeviceDetailDialog({ device, onClose }: { device: DeviceRecord; onClose: () => void }) {
  const { data } = usePoll(() => api.deviceMetrics(device.mac, 100), 20000)
  const samples = data?.samples ?? []
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl border-border bg-popover">
        <DialogHeader>
          <DialogTitle>{device.hostname || device.mdns_name || device.ip}</DialogTitle>
          <DialogDescription className="font-mono text-xs">
            {device.ip} · {device.mac}
            {device.vendor ? ` · ${device.vendor}` : ''}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          <Mini data={samples} dataKey="latency_ms" color="#22d3ee" unit=" ms" title="Latencia" decimals={1} />
          <Mini data={samples} dataKey="quality" color="#38bdf8" unit="/100" title="Calidad" />
          <Mini data={samples} dataKey="jitter_ms" color="#2de2e6" unit=" ms" title="Jitter" decimals={1} />
          <Mini data={samples} dataKey="packet_loss_pct" color="#fbbf24" unit="%" title="Pérdida" decimals={1} />
        </div>
      </DialogContent>
    </Dialog>
  )
}
