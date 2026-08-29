import { Wifi } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { AnimatedNumber, GlassPanel, Meter } from '@/components/metrics'
import { formatBps, formatBytes, formatUptime, usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import type { SystemStatus as Sys } from '@/types'
import PanelError from './PanelError'

function Sub({ children }: { children: React.ReactNode }) {
  return <span className="block text-[11.5px] text-muted-foreground/80">{children}</span>
}

export default function SystemStatus() {
  // 3 s cadence keeps CPU / network rates lively without hammering the box.
  const { data, error } = usePoll<Sys>(api.system, 3000)
  const online = !error && !!data

  const s = data
  const cpuPct = s?.cpu?.percent ?? 0
  const memPct = s?.memory?.percent ?? 0
  const proc = s?.process
  const server = s?.server
  const fe = s?.frontend
  const mainIface = s?.network?.interfaces?.[0]

  return (
    <GlassPanel
      title="Estado del sistema"
      right={
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 text-[11.5px] font-semibold ${online ? 'text-ok' : 'text-destructive'}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${online ? 'bg-ok' : 'bg-destructive'}`} />
            {online ? 'conectado' : 'sin conexión'}
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
            CPU — {cpuPct.toFixed(0)}%
          </span>
          {s?.cpu?.per_core && s.cpu.per_core.length > 0 && (
            <div className="flex h-[34px] items-end gap-1">
              {s.cpu.per_core.slice(0, 16).map((c, i) => (
                <div key={i} title={`core ${i}: ${c.toFixed(0)}%`} className="relative h-full flex-1 overflow-hidden rounded-[3px] bg-white/[0.08]">
                  <div
                    className="absolute inset-x-0 bottom-0 rounded-[3px]"
                    style={{ height: `${c}%`, background: 'linear-gradient(180deg, var(--teal), var(--violet))' }}
                  />
                </div>
              ))}
            </div>
          )}
          <Sub>
            {s?.cpu?.logical ?? '—'} núcleos
            {s?.cpu?.freq_mhz ? ` · ${Math.round(s.cpu.freq_mhz)} MHz` : ''}
          </Sub>
          {s?.cpu?.load_avg?.length ? <Sub>load {s.cpu.load_avg.map((n) => n.toFixed(1)).join(' ')}</Sub> : null}
        </div>

        {/* Memory & disk */}
        <div className="flex flex-col gap-3">
          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">memoria</span>
            <div className="text-xl font-extrabold leading-tight">
              {formatBytes(s?.memory?.used)}{' '}
              <span className="text-[13px] font-semibold text-muted-foreground">/ {formatBytes(s?.memory?.total)}</span>
            </div>
          </div>
          <Meter percent={memPct} />
          {s?.disks?.slice(0, 2).map((d) => (
            <div key={d.mount}>
              <Sub>
                disco {d.mount} — {d.percent.toFixed(0)}% usado
              </Sub>
              <Meter percent={d.percent} gradient="blue-teal" />
            </div>
          ))}
        </div>

        {/* Network I/O */}
        <div className="flex flex-col gap-2.5">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            red{mainIface ? ` — ${mainIface.name}` : ''}
          </span>
          {mainIface ? (
            <div className="flex gap-5">
              <div className="flex flex-col gap-0.5">
                <span className="text-[11px] font-bold" style={{ color: 'var(--teal)' }}>
                  ↓ BAJADA
                </span>
                <span className="text-lg font-extrabold leading-none">{formatBps(mainIface.down_bps)}</span>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-[11px] font-bold" style={{ color: 'var(--pink)' }}>
                  ↑ SUBIDA
                </span>
                <span className="text-lg font-extrabold leading-none">{formatBps(mainIface.up_bps)}</span>
              </div>
            </div>
          ) : (
            <Sub>sin interfaz activa</Sub>
          )}
          <Sub>backend uptime: {formatUptime(server?.uptime_seconds)}</Sub>
          <Sub>
            <AnimatedNumber value={server?.requests_served ?? 0} /> peticiones ·{' '}
            <AnimatedNumber value={server?.scans_completed ?? 0} /> scans
          </Sub>
          <Sub>
            {server?.ws_clients ?? 0} clientes ws ·{' '}
            {server?.auth_enabled ? <span className="text-ok">token</span> : <span className="text-warn">sin auth</span>}
          </Sub>
        </div>

        {/* Build / host */}
        <div className="flex flex-col gap-2.5">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">build / host</span>
          <Sub>
            frontend <span className="font-mono text-foreground/80">{fe?.built ? 'compilado' : 'sin build'}</span>
            {fe?.built_at ? ` · ${new Date(fe.built_at).toLocaleDateString()}` : ''}
          </Sub>
          <Sub>
            backend <span className="font-mono text-foreground/80">netscan-core v{server?.version ?? '—'}</span>
          </Sub>
          <Sub>
            host: {s?.host?.os ?? '—'} {s?.host?.os_release ?? ''} ({s?.host?.arch ?? '—'})
          </Sub>
          <Sub>
            python {proc?.python ?? '—'} · psutil{' '}
            {s?.psutil ? <span className="text-ok">sí</span> : <span className="text-warn">no</span>}
          </Sub>
        </div>
      </div>

      {s?.network?.interfaces && s.network.interfaces.length > 1 && (
        <div className="mt-5 space-y-1.5 border-t border-white/10 pt-4">
          {s.network.interfaces.slice(1, 5).map((n) => (
            <div key={n.name} className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px]">
              <span className="flex w-32 items-center gap-1.5 font-mono">
                <Wifi className={`h-3.5 w-3.5 ${n.is_up ? 'text-ok' : 'text-muted-foreground/40'}`} strokeWidth={1.6} />
                {n.name}
              </span>
              <span className="w-32 font-mono text-muted-foreground">{n.ipv4 || '—'}</span>
              <span className="font-mono text-foreground/80">↓ {formatBps(n.down_bps)}</span>
              <span className="font-mono text-muted-foreground">↑ {formatBps(n.up_bps)}</span>
              <span className="font-mono text-muted-foreground/70">Σ {formatBytes(n.bytes_recv + n.bytes_sent)}</span>
            </div>
          ))}
        </div>
      )}
    </GlassPanel>
  )
}
