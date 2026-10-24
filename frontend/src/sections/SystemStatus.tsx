import { Wifi } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { AnimatedNumber, GlassPanel, Meter } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import { fmtBitRate, fmtByteRate, fmtBytes, fmtDateTime, fmtDuration } from '@/lib/format'
import type { NetIface, SystemStatus as Sys } from '@/types'
import PanelError from './PanelError'
import { useI18n } from '@/i18n/context'

function Sub({ children }: { children: React.ReactNode }) {
  return <span className="block text-xs text-muted-foreground/80">{children}</span>
}

const rx = (n: NetIface) => n.rx_bytes_per_s ?? n.down_bps
const tx = (n: NetIface) => n.tx_bytes_per_s ?? n.up_bps

export default function SystemStatus() {
  const { t, locale } = useI18n()
  // 3 s cadence keeps CPU / network rates lively without hammering the box.
  const { data, error } = usePoll<Sys>(api.system, 3000)
  const online = !error && !!data

  const s = data
  const cpuPct = s?.cpu?.percent ?? 0
  const memPct = s?.memory?.percent ?? 0
  const proc = s?.process
  const server = s?.server
  const fe = s?.frontend
  const ifaces = s?.network?.interfaces ?? []
  // The adapter that carries the LAN (owns NetScan's own IP) — not simply the
  // busiest one, which on Windows is often a Hyper-V/WSL virtual switch.
  const mainIface = ifaces.find((i) => server?.local_ip && i.ipv4 === server.local_ip) ?? ifaces[0]
  const others = ifaces.filter((i) => i !== mainIface).slice(0, 5)

  return (
    <GlassPanel
      title={t('sysTitle')}
      right={
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 text-xs font-semibold ${online ? 'text-ok' : 'text-destructive'}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${online ? 'bg-ok' : 'bg-destructive'}`} />
            {online ? t('connected') : t('disconnected')}
          </span>
          {s?.host && (
            <Badge variant="outline" className="border-white/15 font-mono text-[10px]">
              {s.host.hostname}
            </Badge>
          )}
        </div>
      }
    >
      <PanelError error={error} />

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4">
        {/* CPU */}
        <div className="flex flex-col gap-2.5">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            CPU — {cpuPct.toFixed(0)} %
          </span>
          {s?.cpu?.per_core && s.cpu.per_core.length > 0 && (
            <div className="flex h-[34px] items-end gap-1">
              {s.cpu.per_core.slice(0, 16).map((c, i) => (
                <div key={i} title={`core ${i}: ${c.toFixed(0)} %`} className="relative h-full flex-1 overflow-hidden rounded-[3px] bg-white/[0.08]">
                  <div
                    className="absolute inset-x-0 bottom-0 rounded-[3px]"
                    style={{ height: `${c}%`, background: 'linear-gradient(180deg, var(--accent-cyan), var(--accent-cyan-deep))' }}
                  />
                </div>
              ))}
            </div>
          )}
          <Sub>
            {t('cores', s?.cpu?.logical ?? '—')}
            {s?.cpu?.freq_mhz ? ` · ${Math.round(s.cpu.freq_mhz)} MHz` : ''}
          </Sub>
          {s?.cpu?.load_avg?.length ? <Sub>load {s.cpu.load_avg.map((n) => n.toFixed(2)).join(' ')}</Sub> : null}
          <Sub>
            {t('sysProcess')}: {proc?.cpu_percent != null ? `${proc.cpu_percent.toFixed(1)} %` : '—'} · RSS {fmtBytes(proc?.rss)} · {proc?.threads ?? '—'} threads
          </Sub>
        </div>

        {/* Memory & disk */}
        <div className="flex flex-col gap-3">
          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{t('memory')}</span>
            <div className="text-xl font-extrabold leading-tight">
              {fmtBytes(s?.memory?.used)}{' '}
              <span className="text-[13px] font-semibold text-muted-foreground">/ {fmtBytes(s?.memory?.total)}</span>
            </div>
            {s?.memory?.available_bytes != null && <Sub>{t('memAvailable', fmtBytes(s.memory.available_bytes))}</Sub>}
          </div>
          <Meter percent={memPct} />
          {s?.disks?.slice(0, 2).map((d) => (
            <div key={d.mount}>
              <Sub>
                {t('diskUsed', d.mount, d.percent.toFixed(0))} · {fmtBytes(d.free)} {t('free')}
              </Sub>
              <Meter percent={d.percent} gradient="sky" />
            </div>
          ))}
        </div>

        {/* Network I/O */}
        <div className="flex flex-col gap-2.5">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            {t('network')}
            {mainIface ? ` — ${mainIface.name}` : ''}
          </span>
          {mainIface ? (
            <>
              <div className="flex gap-5">
                <div className="flex flex-col gap-0.5">
                  <span className="text-[11px] font-bold" style={{ color: 'var(--accent-cyan)' }}>
                    ↓ {t('down')}
                  </span>
                  <span className="text-lg font-extrabold leading-none">{fmtByteRate(rx(mainIface))}</span>
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-[11px] font-bold" style={{ color: 'var(--accent-slate)' }}>
                    ↑ {t('up')}
                  </span>
                  <span className="text-lg font-extrabold leading-none">{fmtByteRate(tx(mainIface))}</span>
                </div>
              </div>
              <Sub>
                {mainIface.ipv4 || '—'} · {t('sysLink')} {mainIface.speed_mbps ? fmtBitRate(mainIface.speed_mbps * 1e6) : '—'} · MTU {mainIface.mtu}
              </Sub>
            </>
          ) : (
            <Sub>{t('noIface')}</Sub>
          )}
          <Sub>
            {t('sysGateway')}: <span className="font-mono">{server?.gateway_ip ?? '—'}</span> · {server?.network ?? ''}
          </Sub>
          <Sub>
            {t('sysDiscovery')}:{' '}
            {server?.privileged ? <span className="text-ok">ARP (admin)</span> : <span className="text-warn">{t('modeSweep')}</span>}
          </Sub>
        </div>

        {/* Backend */}
        <div className="flex flex-col gap-2.5">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">backend</span>
          <Sub>
            netscan v{server?.version ?? '—'} · uptime {fmtDuration(server?.uptime_seconds)}
          </Sub>
          <Sub>
            <AnimatedNumber value={server?.requests_served ?? 0} /> {t('requests')} ·{' '}
            <AnimatedNumber value={server?.scans_completed ?? 0} /> scans
            {server?.scans_failed ? <span className="text-destructive"> · {t('sysScansFailed', server.scans_failed)}</span> : null}
          </Sub>
          <Sub>
            {t('sysNextScan')}: {server?.next_scan ? fmtDateTime(server.next_scan, locale) : t('sysSchedulerOff')}
            {server?.scheduler_interval_min ? ` (${server.scheduler_interval_min} min)` : ''}
          </Sub>
          <Sub>
            {server?.ws_clients ?? 0} {t('wsClients')} · {t('sysEvents', server?.events?.events_last_60s ?? 0)} ·{' '}
            {server?.auth_enabled ? <span className="text-ok">token</span> : <span className="text-warn">{t('noAuth')}</span>}
          </Sub>
          <Sub>
            frontend <span className="font-mono text-foreground/80">{fe?.built ? t('built') : t('notBuilt')}</span>
            {fe?.built_at ? ` · ${new Date(fe.built_at).toLocaleDateString(locale)}` : ''} · host {s?.host?.os ?? '—'} {s?.host?.os_release ?? ''} · python {proc?.python ?? '—'}
          </Sub>
        </div>
      </div>

      {others.length > 0 && (
        <div className="mt-5 space-y-1.5 border-t border-white/10 pt-4">
          {others.map((n) => (
            <div key={n.name} className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
              <span className="flex w-40 items-center gap-1.5 truncate font-mono" title={n.name}>
                <Wifi className={`h-3.5 w-3.5 shrink-0 ${n.is_up ? 'text-ok' : 'text-muted-foreground/40'}`} strokeWidth={1.6} />
                {n.name}
              </span>
              <span className="w-32 font-mono text-muted-foreground">{n.ipv4 || '—'}</span>
              <span className="font-mono text-foreground/80">↓ {fmtByteRate(rx(n))}</span>
              <span className="font-mono text-muted-foreground">↑ {fmtByteRate(tx(n))}</span>
              <span className="font-mono text-muted-foreground/70">Σ {fmtBytes(n.bytes_recv + n.bytes_sent)}</span>
            </div>
          ))}
        </div>
      )}
    </GlassPanel>
  )
}
