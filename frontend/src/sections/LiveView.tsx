import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, Area } from 'recharts'
import { GlassPanel } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import { fmtAgo, fmtDuration, fmtMs, fmtPct, rttTone } from '@/lib/format'
import PanelError from './PanelError'
import UptimeBoard from './UptimeBoard'
import { useI18n } from '@/i18n/context'

const TONE = { ok: 'text-ok', warn: 'text-warn', bad: 'text-destructive', none: 'text-muted-foreground' }

function fmtClock(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function Kpi({ label, value, sub, cls = '' }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <div className="glass flex flex-col gap-1 px-4 py-3">
      <span className="kbd-label">
        <span className="text-primary/60">// </span>
        {label}
      </span>
      <span className={`font-display text-[22px] font-extrabold leading-none tabular-nums ${cls}`}>{value}</span>
      {sub && <span className="font-mono text-[10.5px] text-muted-foreground">{sub}</span>}
    </div>
  )
}

/** Real-time view: LAN / gateway / Internet latency from the background
 *  monitor (every few seconds, no scan needed) and the per-device uptime board. */
export default function LiveView() {
  const { t } = useI18n()
  const { data: snap, error } = usePoll(api.live, 3000)
  const series = snap?.series ?? []
  const last = series.length ? series[series.length - 1] : null
  const recent = series.slice(-12) // last minute at 5 s
  const wanLoss = recent.length
    ? recent.reduce((n, p) => n + (p.wan_loss_pct ?? 0), 0) / recent.length
    : null

  return (
    <div className="space-y-[18px]">
      <PanelError error={error} />
      {snap && snap.enabled === false && (
        <p className="glass px-4 py-3 font-mono text-xs text-warn">{t('liveDisabled')}</p>
      )}
      <div className="grid grid-cols-2 gap-[14px] md:grid-cols-3 xl:grid-cols-6">
        <Kpi
          label={t('liveUp')}
          value={`${snap?.online ?? 0} / ${snap?.total ?? 0}`}
          sub={t('liveAnswering', last?.online ?? 0)}
          cls={snap && snap.online < snap.total ? 'text-warn' : 'text-ok'}
        />
        <Kpi label={t('liveLanAvg')} value={fmtMs(last?.latency_ms)} sub={t('liveLanAvgSub')} cls={TONE[rttTone(last?.latency_ms)]} />
        <Kpi
          label={t('liveGateway')}
          value={fmtMs(last?.gateway_ms)}
          sub={snap?.gateway_ip ?? t('liveNoGateway')}
          cls={TONE[rttTone(last?.gateway_ms)]}
        />
        <Kpi
          label={t('liveWan')}
          value={fmtMs(last?.wan_ms)}
          sub={snap?.wan_targets?.length ? snap.wan_targets.join(' · ') : t('liveNoWan')}
          cls={last?.wan_ms == null ? 'text-destructive' : last.wan_ms < 40 ? 'text-ok' : 'text-warn'}
        />
        <Kpi
          label={t('liveWanLoss')}
          value={fmtPct(wanLoss, 0)}
          sub={t('liveLastMinute')}
          cls={wanLoss == null ? '' : wanLoss > 0 ? 'text-warn' : 'text-ok'}
        />
        <Kpi
          label={t('liveMonitor')}
          value={snap?.interval_s ? `${snap.interval_s} s` : '—'}
          sub={`ICMP ${snap?.icmp_backend ?? '?'} · tick ${fmtMs(snap?.tick_ms)} · ${t('liveSince', fmtAgo(snap?.monitoring_since))}`}
        />
      </div>

      <GlassPanel
        title={t('liveTitle')}
        right={
          <span className="flex items-center gap-2 font-mono text-xs text-muted-foreground">
            <span
              className="h-1.5 w-1.5 animate-pulse rounded-full bg-[color:var(--teal)]"
              style={{ boxShadow: '0 0 8px var(--teal)' }}
            />
            {t('liveWindow', fmtDuration(series.length * (snap?.interval_s ?? 5)))}
          </span>
        }
      >
        {series.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">{t('starting')}</p>
        ) : (
          <ResponsiveContainer width="100%" height={230}>
            <ComposedChart data={series} margin={{ top: 6, right: 8, bottom: 0, left: -8 }}>
              <defs>
                <linearGradient id="live-lat" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2de2e6" stopOpacity={0.35} />
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
                minTickGap={60}
              />
              <YAxis
                yAxisId="ms"
                width={52}
                tick={{ fill: 'rgba(233,236,241,0.42)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
                tickFormatter={(v: number) => `${v} ms`}
                tickLine={false}
                axisLine={false}
                domain={[0, 'auto']}
              />
              <YAxis yAxisId="n" orientation="right" hide domain={[0, (max: number) => Math.max(max, 1) * 1.2]} />
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
                formatter={(val: number | string, name: string) =>
                  name === t('liveAnsweringShort') ? [String(val), name] : [fmtMs(Number(val)), name]
                }
              />
              <Legend wrapperStyle={{ fontSize: 11, fontFamily: 'JetBrains Mono' }} iconType="plainline" />
              <Area
                yAxisId="ms"
                type="monotone"
                dataKey="latency_ms"
                name={t('liveLanAvg')}
                stroke="#2de2e6"
                strokeWidth={2}
                fill="url(#live-lat)"
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              <Line yAxisId="ms" type="monotone" dataKey="gateway_ms" name={t('liveGateway')} stroke="#c4a7ff" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
              <Line yAxisId="ms" type="monotone" dataKey="wan_ms" name={t('liveWan')} stroke="#ffbe37" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
              <Line yAxisId="n" type="stepAfter" dataKey="online" name={t('liveAnsweringShort')} stroke="#36e09e" strokeOpacity={0.6} strokeDasharray="3 3" strokeWidth={1} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
        <p className="mt-2 font-mono text-[10.5px] text-muted-foreground">{t('liveChartNote', snap?.down_after ?? 3, snap?.interval_s ?? 5)}</p>
      </GlassPanel>

      <UptimeBoard />
    </div>
  )
}
