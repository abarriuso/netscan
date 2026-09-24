import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { GlassPanel } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import type { LiveDevice } from '@/types'
import PanelError from './PanelError'

function fmtClock(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function DeviceTile({ d }: { d: LiveDevice }) {
  return (
    <div className={`glass card-hover flex flex-col gap-1 border-l-2 p-3 ${d.up ? 'border-l-ok/70' : 'border-l-destructive/70'} ${d.up ? '' : 'opacity-60'}`}>
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 shrink-0 ${d.up ? 'bg-ok' : 'bg-destructive'}`}
          style={{ boxShadow: d.up ? '0 0 8px #36e09e' : '0 0 8px #ff4a5e' }}
        />
        <span className="truncate text-[13px] font-semibold" title={d.name}>
          {d.name}
        </span>
      </div>
      <div className="flex items-center justify-between font-mono text-[11px]">
        <span className="text-muted-foreground">{d.ip}</span>
        <span className={d.up ? 'text-primary' : 'text-destructive'}>
          {d.up ? `${d.latency_ms}ms` : 'sin respuesta'}
        </span>
      </div>
    </div>
  )
}

/** Real-time view: a live latency chart fed by the backend's background ping,
 *  plus a status map of every known device (up/down + current RTT). */
export default function LiveView() {
  const { data: snap, error } = usePoll(api.live, 3000)
  const series = snap?.series ?? []
  const devices = snap?.devices ?? []
  const last = series.length ? series[series.length - 1] : null
  const hasLive = series.length > 0 || devices.length > 0

  return (
    <div className="space-y-[18px]">
      <PanelError error={error} />
      <GlassPanel
        title="Latencia de red en vivo"
        right={
          <span className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
            <span
              className="h-1.5 w-1.5 animate-pulse rounded-full bg-[color:var(--teal)]"
              style={{ boxShadow: '0 0 8px var(--teal)' }}
            />
            en vivo · {snap?.online ?? 0}/{snap?.total ?? 0} online
            {last?.latency_ms != null && <span className="text-foreground/90">· {last.latency_ms} ms</span>}
          </span>
        }
      >
        {!hasLive ? (
          <p className="py-10 text-center text-sm text-muted-foreground">arrancando el monitor… (unos segundos)</p>
        ) : (
          <ResponsiveContainer width="100%" height={190}>
            <AreaChart data={series} margin={{ top: 6, right: 10, bottom: 0, left: -12 }}>
              <defs>
                <linearGradient id="live-lat" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2de2e6" stopOpacity={0.42} />
                  <stop offset="100%" stopColor="#2de2e6" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(120,200,210,0.07)" vertical={false} />
              <XAxis
                dataKey="t"
                tickFormatter={fmtClock}
                tick={{ fill: 'rgba(233,236,241,0.42)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                tickLine={false}
                axisLine={false}
                minTickGap={50}
              />
              <YAxis
                width={42}
                tick={{ fill: 'rgba(233,236,241,0.42)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                tickLine={false}
                axisLine={false}
                domain={['auto', 'auto']}
              />
              <Tooltip
                contentStyle={{
                  background: 'rgba(11,13,17,0.96)',
                  border: '1px solid rgba(45,226,230,0.35)',
                  borderRadius: 2,
                  fontSize: 12,
                  fontFamily: 'JetBrains Mono',
                }}
                labelStyle={{ color: 'rgba(233,236,241,0.6)' }}
                labelFormatter={(v) => fmtClock(String(v))}
                formatter={(val: number | string) => [`${val} ms`, 'latencia media']}
              />
              <Area
                type="monotone"
                dataKey="latency_ms"
                stroke="#2de2e6"
                strokeWidth={2}
                fill="url(#live-lat)"
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </GlassPanel>

      <GlassPanel title="Mapa de red" meta={`${devices.length} equipos`}>
        {devices.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            sin equipos todavía — lanza un scan para poblar el inventario
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            {devices.map((d) => (
              <DeviceTile key={d.mac} d={d} />
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  )
}
