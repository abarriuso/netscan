import { useState } from 'react'
import { Area, AreaChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Gauge, Power, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { toast } from 'sonner'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { RoleIcon } from '@/components/RoleIcon'
import UptimeBar from '@/components/UptimeBar'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import { closeDeviceDetail, useDeviceDetailTarget } from '@/lib/deviceDetail'
import { fmtAvailability, fmtDateTime, fmtDuration, fmtMs, fmtMbps, fmtPct } from '@/lib/format'
import type { MetricSamplePoint } from '@/types'
import { FactorList, RiskBadge } from './SecurityPanel'
import { useI18n } from '@/i18n/context'

function fmtT(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const today = d.toDateString() === new Date().toDateString()
  return today
    ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleString([], { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const TOOLTIP_STYLE = {
  background: 'rgba(11,13,17,0.96)',
  border: '1px solid rgba(45,226,230,0.35)',
  borderRadius: 2,
  fontSize: 12,
  fontFamily: 'JetBrains Mono',
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
  const { t } = useI18n()
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
        <p className="py-6 text-center text-[11px] text-muted-foreground">{t('noHistory')}</p>
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
              contentStyle={TOOLTIP_STYLE}
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

function KV({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(120px,auto)_1fr] gap-x-4 gap-y-1 font-mono text-xs">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

const EVENT_COLOR: Record<string, string> = {
  new: 'text-primary',
  up: 'text-ok',
  down: 'text-destructive',
  ip_changed: 'text-warn',
  ports_changed: 'text-warn',
  conflict: 'text-destructive',
  gateway_mac_changed: 'text-destructive',
  trusted: 'text-ok',
  untrusted: 'text-warn',
}

/** Keyed by the stored notes, so a fresh server value resets the draft
 *  without syncing state inside an effect. */
function NotesEditor({ mac, initial, btn }: { mac: string; initial: string; btn: string }) {
  const { t } = useI18n()
  const [notes, setNotes] = useState(initial)
  const save = async () => {
    try {
      await api.setNotes(mac, notes)
      toast.success(t('notesSaved'))
    } catch (e) {
      toast.error(t('notesFailed'), { description: (e as Error).message })
    }
  }
  return (
    <div>
      <label className="mb-1 block font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground">{t('ddNotes')}</label>
      <div className="flex gap-2">
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          maxLength={2000}
          className="min-w-0 flex-1 rounded-none border border-border bg-secondary p-2 font-mono text-xs outline-none focus:border-primary/60"
        />
        <button className={btn} onClick={save} disabled={notes === initial}>
          {t('save')}
        </button>
      </div>
    </div>
  )
}

/** Mounted once in Home; opens for whatever device openDeviceDetail(mac) names. */
export default function DeviceDetailHost() {
  const mac = useDeviceDetailTarget()
  if (!mac) return null
  return <DeviceDetailDialog key={mac} mac={mac} />
}

function DeviceDetailDialog({ mac }: { mac: string }) {
  const { t, locale } = useI18n()
  const { data: profile, error, refresh } = usePoll(() => api.deviceProfile(mac), 15000)
  const { data: metrics } = usePoll(() => api.deviceMetrics(mac, 100), 30000)
  const { data: uptime } = usePoll(() => api.deviceUptime(mac, 24, 96), 30000)
  const { data: timeline } = usePoll(() => api.deviceTimeline(mac), 30000)
  const [testing, setTesting] = useState(false)
  const dev = profile?.device

  const samples = metrics?.samples ?? []
  const up = uptime?.device
  const name = dev ? dev.hostname || dev.mdns_name || dev.ip : mac

  const toggleTrust = async () => {
    if (!dev) return
    try {
      await api.setTrusted(dev.mac, !dev.trusted)
      toast.success(!dev.trusted ? t('markedTrusted') : t('trustRemoved'), { description: name })
      refresh()
    } catch (e) {
      toast.error(t('trustFailed'), { description: (e as Error).message })
    }
  }
  const speedtest = async () => {
    if (!dev) return
    setTesting(true)
    try {
      const r = await api.speedtest(dev.mac)
      toast.success(t('speedtestDone'), {
        description: `${fmtMs(r.metrics.latency_avg_ms)} (${r.metrics.rtt_source || 'n/a'}) · jitter ${fmtMs(r.metrics.jitter_ms)} · loss ${fmtPct(r.metrics.packet_loss_pct)} · Q ${r.metrics.quality ?? '—'}/100`,
      })
      refresh()
    } catch (e) {
      toast.error(t('speedtestFailed'), { description: (e as Error).message })
    } finally {
      setTesting(false)
    }
  }
  const wake = async () => {
    if (!dev) return
    try {
      const r = await api.wake(dev.mac)
      toast(t('wolSent'), { description: `${name} · UDP ${r.broadcast ?? ''}:9` })
    } catch (e) {
      toast.error(t('wolFailed'), { description: (e as Error).message })
    }
  }
  const btn =
    'press flex items-center gap-1.5 rounded-none border border-border bg-secondary px-2.5 py-1.5 font-mono text-[11px] text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary disabled:opacity-50'

  return (
    <Dialog open onOpenChange={(o) => !o && closeDeviceDetail()}>
      <DialogContent className="max-h-[90vh] max-w-4xl overflow-y-auto border-border bg-popover">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            {profile && <RoleIcon role={profile.classification.role} className="h-5 w-5" />}
            {name}
            {profile && <RiskBadge score={profile.risk.score} level={profile.risk.level} />}
            {dev && (
              <span className={`border px-1.5 py-0.5 font-mono text-[10.5px] uppercase ${dev.online ? 'border-ok/50 text-ok' : 'border-destructive/50 text-destructive'}`}>
                {dev.online ? 'up' : 'down'}
                {profile?.live?.method ? ` · ${profile.live.method}` : ''}
              </span>
            )}
          </DialogTitle>
          <DialogDescription className="font-mono text-xs">
            {dev ? `${dev.ip} · ${dev.mac}${dev.vendor ? ` · ${dev.vendor}` : ''}` : mac}
          </DialogDescription>
        </DialogHeader>
        {error && <p className="font-mono text-xs text-destructive">{error}</p>}

        <div className="flex flex-wrap gap-2">
          <button className={btn} onClick={toggleTrust} disabled={!dev}>
            {dev?.trusted ? <ShieldCheck className="h-3.5 w-3.5 text-ok" /> : <ShieldQuestion className="h-3.5 w-3.5 text-destructive" />}
            {dev?.trusted ? t('verified') : t('markTrusted')}
          </button>
          <button className={btn} onClick={speedtest} disabled={!dev || testing}>
            <Gauge className={`h-3.5 w-3.5 ${testing ? 'animate-spin' : ''}`} />
            {t('speedtestTitle')}
          </button>
          <button className={btn} onClick={wake} disabled={!dev}>
            <Power className="h-3.5 w-3.5" /> Wake-on-LAN
          </button>
        </div>

        <Tabs defaultValue="overview" className="mt-1">
          {/* A grid, not flex-wrap: the triggers' base height is a percentage
              of the list, so a wrapped second row didn't grow the list and
              was painted over the tab content. */}
          <TabsList
            data-testid="device-tabs"
            className="grid h-auto w-full grid-cols-3 gap-0 rounded-none border border-border bg-card p-0 sm:grid-cols-6"
          >
            {(['overview', 'uptime', 'metrics', 'services', 'risk', 'timeline'] as const).map((k) => (
              <TabsTrigger
                key={k}
                value={k}
                className="h-auto min-w-0 truncate rounded-none border-r border-border/70 px-3 py-2 font-mono text-[11px] uppercase tracking-wider data-[state=active]:bg-primary/[0.08] data-[state=active]:text-primary"
              >
                {t(`dd_${k}` as const)}
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="overview" className="space-y-4 pt-3">
            {profile && dev && (
              <>
                <KV
                  rows={[
                    [t('ddRole'), <span>{t('role', profile.classification.role)} <span className="text-muted-foreground">({profile.classification.confidence} % · {profile.classification.reasons.join(' · ')})</span></span>],
                    ['hostname', dev.hostname || '—'],
                    ['mDNS', `${dev.mdns_name || '—'}${profile.mdns_services.length ? ` [${profile.mdns_services.join(', ')}]` : ''}`],
                    ['vendor / OUI', `${dev.vendor || '—'} · ${profile.mac_info.oui}`],
                    [
                      'MAC',
                      profile.mac_info.virtual_platform
                        ? t('ddVirtualMac', profile.mac_info.virtual_platform)
                        : profile.mac_info.randomized
                          ? t('ddRandomMac')
                          : t('ddGlobalMac'),
                    ],
                    ['OS', dev.os_guess || '—'],
                    [t('ddFirstSeen'), fmtDateTime(dev.first_seen, locale)],
                    [t('ddLastSeen'), fmtDateTime(dev.last_seen, locale)],
                    [t('colLatency'), `${fmtMs(dev.last_latency_ms)} · jitter ${fmtMs(dev.jitter_ms)} · ${t('colLoss')} ${fmtPct(dev.packet_loss_pct)} · TCP ${fmtMs(dev.tcp_connect_avg_ms)}`],
                    [t('colQuality'), dev.quality != null ? `${dev.quality}/100` : '—'],
                    ['throughput', fmtMbps(dev.throughput_mbps)],
                  ]}
                />
                <NotesEditor key={`${dev.mac}:${dev.notes ?? ''}`} mac={dev.mac} initial={dev.notes ?? ''} btn={btn} />
              </>
            )}
          </TabsContent>

          <TabsContent value="uptime" className="space-y-4 pt-3">
            {up ? (
              <>
                <div className="grid grid-cols-2 gap-2 font-mono text-xs sm:grid-cols-4">
                  {(['1h', '24h', '7d', '30d'] as const).map((w) => (
                    <div key={w} className="border border-border/70 px-3 py-2">
                      <span className="block text-[10px] uppercase text-muted-foreground">{w}</span>
                      <span className="text-[15px] font-bold">{fmtAvailability(up.windows[w].availability_pct)}</span>
                      <span className="block text-[10px] text-muted-foreground">{t('uptimeCov', (up.windows[w].coverage_pct ?? 0).toFixed(1))}</span>
                    </div>
                  ))}
                </div>
                <UptimeBar slots={up.timeline} slotS={uptime!.slot_s} height={30} locale={locale} noDataLabel={t('uptimeNoData')} />
                <ResponsiveContainer width="100%" height={170}>
                  <ComposedChart data={up.timeline} margin={{ top: 4, right: 6, bottom: 0, left: -10 }}>
                    <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
                    <XAxis dataKey="start" tickFormatter={fmtT} tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }} tickLine={false} axisLine={false} minTickGap={40} />
                    <YAxis width={52} tickFormatter={(v: number) => `${v} ms`} tick={{ fill: 'rgba(255,255,255,0.4)', fontSize: 9 }} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(v) => fmtT(String(v))} formatter={(v: number | string, n: string) => [fmtMs(Number(v)), n]} />
                    <Area type="monotone" dataKey="rtt_max_ms" name="RTT max" stroke="#ff4a5e" strokeOpacity={0.4} fill="#ff4a5e" fillOpacity={0.06} dot={false} connectNulls isAnimationActive={false} />
                    <Line type="monotone" dataKey="rtt_avg_ms" name="RTT avg" stroke="#2de2e6" strokeWidth={2} dot={false} connectNulls isAnimationActive={false} />
                    <Line type="monotone" dataKey="rtt_min_ms" name="RTT min" stroke="#36e09e" strokeWidth={1} dot={false} connectNulls isAnimationActive={false} />
                  </ComposedChart>
                </ResponsiveContainer>
                <KV
                  rows={[
                    [t('uptimeOutages'), `${up.outages_24h} (24 h) · ${up.outages_30d} (30 d)`],
                    ['MTTR', fmtDuration(up.mttr_s)],
                    [t('ddLongest'), fmtDuration(up.longest_outage_s)],
                  ]}
                />
                {up.outages.length > 0 && (
                  <table className="w-full font-mono text-xs">
                    <tbody>
                      {[...up.outages].reverse().map((o) => (
                        <tr key={o.start} className="border-t border-border/40">
                          <td className="py-1 text-destructive">▼ {fmtDateTime(o.start, locale)}</td>
                          <td>{o.end ? `▲ ${fmtDateTime(o.end, locale)}` : <span className="text-destructive">{t('ddOngoing')}</span>}</td>
                          <td className="text-right">{fmtDuration(o.duration_s)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">{t('noHistory')}</p>
            )}
          </TabsContent>

          <TabsContent value="metrics" className="pt-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Mini data={samples} dataKey="latency_ms" color="#22d3ee" unit=" ms" title={t('chartLatency')} decimals={2} />
              <Mini data={samples} dataKey="quality" color="#38bdf8" unit="/100" title={t('chartQuality')} />
              <Mini data={samples} dataKey="jitter_ms" color="#2de2e6" unit=" ms" title="Jitter" decimals={2} />
              <Mini data={samples} dataKey="packet_loss_pct" color="#fbbf24" unit=" %" title={t('chartLoss')} decimals={1} />
            </div>
            <p className="mt-2 font-mono text-[10.5px] text-muted-foreground">{t('ddMetricsNote')}</p>
          </TabsContent>

          <TabsContent value="services" className="space-y-3 pt-3">
            {profile && (
              <>
                <table className="w-full font-mono text-xs">
                  <thead className="text-left text-[10.5px] uppercase tracking-wider text-muted-foreground">
                    <tr>
                      <th className="py-1 font-medium">{t('colPorts')}</th>
                      <th className="font-medium">{t('ddService')}</th>
                      <th className="font-medium">{t('ddVersion')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {profile.ports.map((p) => (
                      <tr key={p.port} className="border-t border-border/40">
                        <td className="py-1 text-primary">{p.port}/tcp</td>
                        <td>{p.service}</td>
                        <td className="text-muted-foreground">{p.version || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {profile.http.map((h) => (
                  <div key={h.url} className="border border-border/60 p-2.5 font-mono text-xs">
                    <a href={h.url} target="_blank" rel="noreferrer" className="font-semibold hover:text-primary">
                      {h.url}
                    </a>
                    <p className="text-muted-foreground">
                      {h.status_code ? `HTTP ${h.status_code}` : t('ddNoResponse')}
                      {h.server ? ` · ${h.server}` : ''}
                      {h.title ? ` · “${h.title}”` : ''}
                      {h.final_url ? ` → ${h.final_url}` : ''}
                    </p>
                    {h.error && <p className="text-warn">{h.error}</p>}
                    {h.tls && (
                      <p className="text-muted-foreground">
                        {h.tls.version} · {h.tls.subject} · {h.tls.issuer} ·{' '}
                        <span className={(h.tls.days_remaining ?? 0) < 14 ? 'text-warn' : 'text-ok'}>
                          {h.tls.days_remaining} d
                        </span>
                        {h.tls.self_signed ? ` · ${t('secSelfSigned')}` : ''}
                      </p>
                    )}
                    {(h.tech ?? []).length > 0 && <p className="text-[color:var(--accent-sky)]">{h.tech!.join(' · ')}</p>}
                  </div>
                ))}
              </>
            )}
          </TabsContent>

          <TabsContent value="risk" className="pt-3">
            {profile && (
              <>
                <p className="mb-3 font-mono text-xs text-muted-foreground">{t('ddRiskIntro')}</p>
                <FactorList device={profile.risk} />
              </>
            )}
          </TabsContent>

          <TabsContent value="timeline" className="pt-3">
            {(timeline?.events ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('noHistory')}</p>
            ) : (
              <ol className="space-y-1 font-mono text-xs">
                {timeline!.events.map((e, i) => (
                  <li key={i} className="grid grid-cols-[150px_110px_1fr] gap-2 border-l-2 border-border/70 pl-2">
                    <span className="text-muted-foreground">{fmtDateTime(e.at, locale)}</span>
                    <span className={EVENT_COLOR[e.kind] ?? ''}>{e.kind}</span>
                    <span className="break-words">{e.detail}</span>
                  </li>
                ))}
              </ol>
            )}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
