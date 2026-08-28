import {
  Activity,
  Cpu,
  Database,
  HardDrive,
  MemoryStick,
  MonitorSmartphone,
  Network,
  Radio,
  Server,
  Wifi,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AnimatedNumber, Meter } from '@/components/metrics'
import { formatBps, formatBytes, formatUptime, usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import type { SystemStatus as Sys } from '@/types'
import PanelError from './PanelError'

function Tile({
  icon: Icon,
  title,
  children,
  right,
}: {
  icon: typeof Server
  title: string
  children: React.ReactNode
  right?: React.ReactNode
}) {
  return (
    <div className="bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Icon className="h-3.5 w-3.5" strokeWidth={1.6} />
          <span className="font-mono text-[10.5px] uppercase tracking-wider">{title}</span>
        </div>
        {right}
      </div>
      {children}
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="text-muted-foreground/70">{label}</span>
      <span className="truncate font-mono text-foreground">{value}</span>
    </div>
  )
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

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0 pb-4">
        <div>
          <CardTitle className="font-mono text-sm uppercase tracking-wider">estado del sistema</CardTitle>
          <p className="mt-1 max-w-prose text-xs text-muted-foreground">
            Todo lo que NetScan sabe de la máquina que lo aloja: el proceso backend, el build del
            frontend y el host — CPU, memoria, disco y tráfico por interfaz, vía{' '}
            <code>psutil</code>.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[11px] ${
              online ? 'text-ok' : 'text-destructive'
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${online ? 'bg-ok' : 'bg-destructive'}`} />
            {online ? 'conectado' : 'sin conexión'}
          </span>
          {s?.host && (
            <Badge variant="outline" className="font-mono text-[10px]">
              {s.host.hostname}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <PanelError error={error} />

        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2 xl:grid-cols-3">
          {/* Terminal server / backend */}
          <Tile
            icon={Server}
            title="terminal server (backend)"
            right={
              server?.scan_in_progress ? (
                <Badge className="animate-pulse font-mono text-[10px]">escaneando</Badge>
              ) : (
                <Badge variant="outline" className="font-mono text-[10px]">
                  v{server?.version ?? '—'}
                </Badge>
              )
            }
          >
            <div className="space-y-1.5">
              <Row label="uptime" value={formatUptime(server?.uptime_seconds)} />
              <Row
                label="peticiones"
                value={<AnimatedNumber value={server?.requests_served ?? 0} />}
              />
              <Row label="escaneos" value={<AnimatedNumber value={server?.scans_completed ?? 0} />} />
              <Row
                label="último scan"
                value={server?.last_scan_duration_s != null ? `${server.last_scan_duration_s}s` : '—'}
              />
              <Row label="clientes ws" value={server?.ws_clients ?? 0} />
              <Row label="API" value={`${server?.api_host ?? '—'}:${server?.api_port ?? ''}`} />
              <Row
                label="auth"
                value={
                  server?.auth_enabled ? (
                    <span className="text-ok">token</span>
                  ) : (
                    <span className="text-warn">abierto</span>
                  )
                }
              />
              <Row
                label="scheduler"
                value={
                  server?.scheduler_interval_min ? `cada ${server.scheduler_interval_min}m` : 'desactivado'
                }
              />
            </div>
          </Tile>

          {/* Frontend / dashboard */}
          <Tile
            icon={MonitorSmartphone}
            title="frontend (dashboard)"
            right={
              <Badge variant={fe?.built ? 'outline' : 'outline'} className="font-mono text-[10px]">
                {fe?.built ? 'compilado' : 'sin build'}
              </Badge>
            }
          >
            <div className="space-y-1.5">
              <Row label="servido por" value={fe?.served_by_backend ? 'backend (integrado)' : 'dev server'} />
              <Row label="ficheros" value={fe?.files ?? '—'} />
              <Row label="tamaño" value={fe?.size_bytes ? formatBytes(fe.size_bytes) : '—'} />
              <Row label="build" value={fe?.built_at ? new Date(fe.built_at).toLocaleString() : '—'} />
              <Row label="conexión API" value={online ? <span className="text-ok">ok</span> : <span className="text-destructive">caída</span>} />
            </div>
          </Tile>

          {/* CPU */}
          <Tile
            icon={Cpu}
            title="cpu"
            right={
              <span className="font-mono text-xs">
                <AnimatedNumber value={cpuPct} decimals={0} suffix="%" />
              </span>
            }
          >
            <div className="space-y-2">
              <Meter percent={cpuPct} />
              <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                <Row label="núcleos" value={`${s?.cpu?.logical ?? '—'}`} />
                <Row label="físicos" value={`${s?.cpu?.physical ?? '—'}`} />
                <Row label="freq" value={s?.cpu?.freq_mhz ? `${Math.round(s.cpu.freq_mhz)} MHz` : '—'} />
                <Row
                  label="load"
                  value={s?.cpu?.load_avg?.length ? s.cpu.load_avg.map((n) => n.toFixed(1)).join(' ') : '—'}
                />
              </div>
              {s?.cpu?.per_core && s.cpu.per_core.length > 0 && (
                <div className="flex flex-wrap gap-1 pt-1">
                  {s.cpu.per_core.slice(0, 32).map((c, i) => (
                    <div
                      key={i}
                      title={`core ${i}: ${c.toFixed(0)}%`}
                      className="h-6 w-1.5 overflow-hidden rounded-sm bg-muted"
                    >
                      <div
                        className={`w-full transition-[height] duration-500 ${
                          c < 60 ? 'bg-muted-foreground/40' : c < 85 ? 'bg-warn' : 'bg-destructive'
                        }`}
                        style={{ height: `${c}%`, marginTop: `${100 - c}%` }}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Tile>

          {/* Memory */}
          <Tile
            icon={MemoryStick}
            title="memoria"
            right={
              <span className="font-mono text-xs">
                <AnimatedNumber value={memPct} decimals={0} suffix="%" />
              </span>
            }
          >
            <div className="space-y-2">
              <Meter percent={memPct} label="RAM" value={`${formatBytes(s?.memory?.used)} / ${formatBytes(s?.memory?.total)}`} />
              {s?.memory?.swap_total ? (
                <Meter
                  percent={s.memory.swap_percent ?? 0}
                  label="swap"
                  value={`${formatBytes(s.memory.swap_used)} / ${formatBytes(s.memory.swap_total)}`}
                />
              ) : null}
              <Row label="libre" value={formatBytes(s?.memory?.free)} />
            </div>
          </Tile>

          {/* Process */}
          <Tile icon={Activity} title="proceso backend">
            <div className="space-y-1.5">
              <Row label="pid" value={proc?.pid ?? '—'} />
              <Row label="cpu proc" value={proc?.cpu_percent != null ? `${proc.cpu_percent}%` : '—'} />
              <Row label="rss" value={formatBytes(proc?.rss ?? undefined)} />
              <Row label="hilos" value={proc?.threads ?? '—'} />
              <Row label="conexiones" value={proc?.connections ?? '—'} />
              <Row label="python" value={proc?.python ?? '—'} />
            </div>
          </Tile>

          {/* Host */}
          <Tile icon={Radio} title="host">
            <div className="space-y-1.5">
              <Row label="SO" value={`${s?.host?.os ?? '—'} ${s?.host?.os_release ?? ''}`} />
              <Row label="arch" value={s?.host?.arch ?? '—'} />
              <Row label="uptime" value={formatUptime(s?.host?.uptime_seconds ?? undefined)} />
              <Row
                label="psutil"
                value={s?.psutil ? <span className="text-ok">sí</span> : <span className="text-warn">no</span>}
              />
            </div>
          </Tile>
        </div>

        {/* Disks */}
        {s?.disks && s.disks.length > 0 && (
          <div className="rounded-lg border border-border p-3">
            <div className="mb-2 flex items-center gap-2 text-muted-foreground">
              <HardDrive className="h-3.5 w-3.5" strokeWidth={1.6} />
              <span className="font-mono text-[10.5px] uppercase tracking-wider">discos</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {s.disks.slice(0, 6).map((d) => (
                <Meter
                  key={d.mount}
                  percent={d.percent}
                  label={`${d.mount} (${d.fstype})`}
                  value={`${formatBytes(d.used)} / ${formatBytes(d.total)}`}
                />
              ))}
            </div>
          </div>
        )}

        {/* Network interfaces */}
        {s?.network?.interfaces && s.network.interfaces.length > 0 && (
          <div className="rounded-lg border border-border p-3">
            <div className="mb-2 flex items-center gap-2 text-muted-foreground">
              <Network className="h-3.5 w-3.5" strokeWidth={1.6} />
              <span className="font-mono text-[10.5px] uppercase tracking-wider">
                interfaces de red — tráfico en vivo, con link speed del adaptador
              </span>
            </div>
            <div className="space-y-2">
              {s.network.interfaces.slice(0, 6).map((n) => (
                <div key={n.name} className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md px-1 py-1 text-xs">
                  <span className="flex w-32 items-center gap-1.5 font-mono">
                    <Wifi className={`h-3.5 w-3.5 ${n.is_up ? 'text-ok' : 'text-muted-foreground/40'}`} strokeWidth={1.6} />
                    {n.name}
                  </span>
                  <span className="w-32 font-mono text-muted-foreground">{n.ipv4 || '—'}</span>
                  <span className="font-mono">
                    {n.speed_mbps ? `${n.speed_mbps >= 1000 ? n.speed_mbps / 1000 + 'G' : n.speed_mbps + 'M'}` : '—'}
                  </span>
                  <span className="font-mono text-foreground">↓ {formatBps(n.down_bps)}</span>
                  <span className="font-mono text-muted-foreground">↑ {formatBps(n.up_bps)}</span>
                  <span className="font-mono text-muted-foreground/70">
                    Σ {formatBytes(n.bytes_recv + n.bytes_sent)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* DB */}
        <div className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs">
          <Database className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.6} />
          <span className="text-muted-foreground">base de datos:</span>
          <span className="truncate font-mono">{server?.db_url ?? '—'}</span>
        </div>
      </CardContent>
    </Card>
  )
}
