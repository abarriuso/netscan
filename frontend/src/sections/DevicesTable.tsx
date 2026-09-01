import { useMemo, useState } from 'react'
import { Gauge, Power, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { GlassPanel, QualityBadge } from '@/components/metrics'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import type { DeviceRecord, PortInfo } from '@/types'
import PanelError from './PanelError'

function portsOf(dev: DeviceRecord): PortInfo[] {
  try {
    return JSON.parse(dev.open_ports_json) as PortInfo[]
  } catch {
    return []
  }
}

export default function DevicesTable({ refreshKey }: { refreshKey: number }) {
  const { data: devices, error, refresh } = usePoll(api.devices, 15000, refreshKey)
  const loading = devices == null && !error
  const [filter, setFilter] = useState('')
  const [testing, setTesting] = useState<Set<string>>(new Set())

  const runSpeedtest = async (mac: string) => {
    setTesting((s) => new Set(s).add(mac))
    try {
      await api.speedtest(mac)
      refresh()
    } finally {
      setTesting((s) => {
        const next = new Set(s)
        next.delete(mac)
        return next
      })
    }
  }

  const filtered = useMemo(() => {
    const list = devices ?? []
    const q = filter.toLowerCase()
    if (!q) return list
    return list.filter((d) =>
      [d.ip, d.mac, d.hostname, d.vendor, d.mdns_name, d.os_guess]
        .join(' ')
        .toLowerCase()
        .includes(q),
    )
  }, [devices, filter])

  const toggleTrust = async (dev: DeviceRecord) => {
    await api.setTrusted(dev.mac, !dev.trusted)
    refresh()
  }

  return (
    <GlassPanel
      title="Dispositivos"
      right={
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          <span className="shrink-0 text-[11.5px] font-medium text-muted-foreground">{filtered.length} descubiertos</span>
          <Input
            placeholder="filtrar…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="h-7 w-28 min-w-0 border-white/15 bg-white/5 text-xs sm:w-40"
          />
        </div>
      }
      contentClassName="-mx-5 -mb-2"
    >
      <div className="px-5">
        <PanelError error={error} />
      </div>
      <div className="max-h-[520px] overflow-auto px-5 pb-2">
        <Table>
          <TableHeader className="[&_tr]:border-white/10">
            <TableRow className="border-white/10 hover:bg-transparent">
              <TableHead className="text-[10.5px] uppercase tracking-wider text-muted-foreground">Host</TableHead>
              <TableHead className="text-[10.5px] uppercase tracking-wider text-muted-foreground">IP / MAC</TableHead>
              <TableHead className="text-right text-[10.5px] uppercase tracking-wider text-muted-foreground">Latencia</TableHead>
              <TableHead className="hidden text-right text-[10.5px] uppercase tracking-wider text-muted-foreground md:table-cell">Jitter</TableHead>
              <TableHead className="hidden text-right text-[10.5px] uppercase tracking-wider text-muted-foreground md:table-cell">Pérdida</TableHead>
              <TableHead className="text-[10.5px] uppercase tracking-wider text-muted-foreground">Calidad</TableHead>
              <TableHead className="hidden text-[10.5px] uppercase tracking-wider text-muted-foreground lg:table-cell">OS</TableHead>
              <TableHead className="text-[10.5px] uppercase tracking-wider text-muted-foreground">Puertos</TableHead>
              <TableHead className="text-[10.5px] uppercase tracking-wider text-muted-foreground">Trust</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading &&
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={`sk-${i}`} className="border-white/[0.06] hover:bg-transparent">
                  <TableCell colSpan={10}>
                    <Skeleton className="h-6 w-full" />
                  </TableCell>
                </TableRow>
              ))}
            {filtered.map((dev) => {
              const ports = portsOf(dev)
              return (
                <TableRow key={dev.mac} className={`border-white/[0.06] transition-colors hover:bg-white/[0.03] ${dev.online ? '' : 'opacity-40'}`}>
                  <TableCell>
                    <div className="font-semibold">{dev.hostname || dev.mdns_name || dev.ip}</div>
                    <div className="text-[11.5px] text-muted-foreground">{dev.vendor || '—'}</div>
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {dev.ip}
                    <br />
                    <span className="text-muted-foreground/70">{dev.mac}</span>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">
                    {dev.last_latency_ms != null ? (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger>{dev.last_latency_ms}ms</TooltipTrigger>
                          <TooltipContent className="font-mono text-xs">
                            handshake TCP medio:{' '}
                            {dev.tcp_connect_avg_ms != null ? `${dev.tcp_connect_avg_ms}ms` : '—'}
                            {dev.throughput_mbps != null && (
                              <div>throughput: {dev.throughput_mbps} Mbps</div>
                            )}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell className="hidden text-right font-mono text-xs text-muted-foreground md:table-cell">
                    {dev.jitter_ms != null ? `${dev.jitter_ms}ms` : '—'}
                  </TableCell>
                  <TableCell className="hidden text-right font-mono text-xs md:table-cell">
                    {dev.packet_loss_pct != null ? (
                      <span
                        className={
                          dev.packet_loss_pct > 20
                            ? 'text-destructive'
                            : dev.packet_loss_pct > 0
                              ? 'text-warn'
                              : 'text-ok'
                        }
                      >
                        {dev.packet_loss_pct}%
                      </span>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>
                    <QualityBadge score={dev.quality} />
                  </TableCell>
                  <TableCell className="hidden text-xs lg:table-cell">
                    {dev.os_guess || <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell className="max-w-64">
                    <div className="flex flex-wrap gap-1">
                      {ports.slice(0, 6).map((p) => (
                        <TooltipProvider key={p.port}>
                          <Tooltip>
                            <TooltipTrigger>
                              <span className="rounded-[5px] border border-primary/30 bg-primary/[0.14] px-1.5 py-0.5 font-mono text-[10.5px] text-[#d7c8ff]">
                                {p.port}
                              </span>
                            </TooltipTrigger>
                            <TooltipContent className="font-mono text-xs">
                              {p.service}
                              {p.version ? ` — ${p.version}` : ''}
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      ))}
                      {ports.length > 6 && (
                        <span className="rounded-[5px] border border-white/15 px-1.5 py-0.5 font-mono text-[10.5px] text-muted-foreground">
                          +{ports.length - 6}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <button
                      onClick={() => toggleTrust(dev)}
                      title={dev.trusted ? 'verificado' : 'marcar como de confianza'}
                      aria-label={dev.trusted ? `quitar confianza de ${dev.ip}` : `marcar ${dev.ip} como de confianza`}
                      className={`flex h-5 w-5 items-center justify-center rounded-full border ${
                        dev.trusted
                          ? 'border-ok/40 bg-ok/[0.16] text-ok'
                          : 'border-destructive/40 bg-destructive/[0.16] text-destructive'
                      }`}
                    >
                      {dev.trusted ? <ShieldCheck className="h-3 w-3" /> : <ShieldQuestion className="h-3 w-3" />}
                    </button>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => runSpeedtest(dev.mac)}
                        disabled={testing.has(dev.mac)}
                        title="Speed test (latencia, jitter, pérdida, TCP)"
                        aria-label={`speed test de ${dev.ip}`}
                        className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] border border-white/10 bg-white/5 text-muted-foreground hover:text-foreground"
                      >
                        <Gauge className={`h-3.5 w-3.5 ${testing.has(dev.mac) ? 'animate-spin' : ''}`} strokeWidth={1.6} />
                      </button>
                      {!dev.online && (
                        <button
                          onClick={() => api.wake(dev.mac)}
                          title="Wake-on-LAN"
                          aria-label={`despertar ${dev.ip} por Wake-on-LAN`}
                          className="flex h-[26px] w-[26px] items-center justify-center rounded-[7px] border border-white/10 bg-white/5 text-muted-foreground hover:text-foreground"
                        >
                          <Power className="h-3.5 w-3.5" strokeWidth={1.6} />
                        </button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              )
            })}
            {!loading && filtered.length === 0 && (
              <TableRow className="border-white/[0.06] hover:bg-transparent">
                <TableCell colSpan={10} className="py-8 text-center text-sm text-muted-foreground">
                  sin dispositivos — lanza un scan
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </GlassPanel>
  )
}
