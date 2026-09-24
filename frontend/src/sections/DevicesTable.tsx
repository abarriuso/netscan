import { lazy, Suspense, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, Check, ChevronsUpDown, Copy, Gauge, Power, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { toast } from 'sonner'
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
import { useCopyToClipboard, usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import type { DeviceRecord, PortInfo } from '@/types'
import PanelError from './PanelError'

const DeviceDetailDialog = lazy(() => import('./DeviceDetailDialog'))

function portsOf(dev: DeviceRecord): PortInfo[] {
  try {
    return JSON.parse(dev.open_ports_json) as PortInfo[]
  } catch {
    return []
  }
}

// Sortable columns and how to extract a comparable value from each device.
// Missing metrics (offline / unmeasured) return null and always sink to the
// bottom regardless of direction, so "worst latency first" shows real data.
type SortKey = 'host' | 'ip' | 'latency' | 'jitter' | 'loss' | 'quality'
const SORT_VALUE: Record<SortKey, (d: DeviceRecord) => number | string | null> = {
  host: (d) => (d.hostname || d.mdns_name || d.ip || '').toLowerCase(),
  ip: (d) => d.ip || '',
  latency: (d) => d.last_latency_ms ?? null,
  jitter: (d) => d.jitter_ms ?? null,
  loss: (d) => d.packet_loss_pct ?? null,
  quality: (d) => d.quality ?? null,
}

function ipToNum(ip: string): number {
  const parts = ip.split('.').map(Number)
  if (parts.length !== 4 || parts.some((n) => Number.isNaN(n))) return -1
  return ((parts[0] << 24) >>> 0) + (parts[1] << 16) + (parts[2] << 8) + parts[3]
}

const lossColor = (pct: number) =>
  pct > 20 ? 'text-destructive' : pct > 0 ? 'text-warn' : 'text-ok'

export default function DevicesTable({ refreshKey }: { refreshKey: number }) {
  const { data: devices, error, refresh } = usePoll(api.devices, 15000, refreshKey)
  const loading = devices == null && !error
  const [detail, setDetail] = useState<DeviceRecord | null>(null)
  const [filter, setFilter] = useState('')
  const [testing, setTesting] = useState<Set<string>>(new Set())
  const [sortKey, setSortKey] = useState<SortKey>('host')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const { copied, copy } = useCopyToClipboard()

  const copyValue = (text: string, label: string) => {
    copy(text).then((ok) => {
      if (ok) toast.success(`${label} copiado`, { description: text })
      else toast.error('No se pudo copiar al portapapeles')
    })
  }

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      // Metrics default to descending (worst-first is what an admin scans for);
      // text columns default to ascending (A→Z).
      setSortDir(key === 'host' || key === 'ip' ? 'asc' : 'desc')
    }
  }

  const runSpeedtest = async (dev: DeviceRecord) => {
    const mac = dev.mac
    setTesting((s) => new Set(s).add(mac))
    try {
      await api.speedtest(mac)
      toast.success('Speed test completado', { description: dev.hostname || dev.ip })
      refresh()
    } catch (e) {
      toast.error('Speed test falló', { description: (e as Error).message })
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
    const matched = !q
      ? list
      : list.filter((d) =>
          [d.ip, d.mac, d.hostname, d.vendor, d.mdns_name, d.os_guess]
            .join(' ')
            .toLowerCase()
            .includes(q),
        )
    const getVal = SORT_VALUE[sortKey]
    const dir = sortDir === 'asc' ? 1 : -1
    return [...matched].sort((a, b) => {
      const va = getVal(a)
      const vb = getVal(b)
      if (va == null && vb == null) return 0
      if (va == null) return 1 // nulls last, always
      if (vb == null) return -1
      if (sortKey === 'ip') return dir * (ipToNum(va as string) - ipToNum(vb as string))
      if (typeof va === 'string' && typeof vb === 'string') return dir * va.localeCompare(vb)
      return dir * ((va as number) - (vb as number))
    })
  }, [devices, filter, sortKey, sortDir])

  const toggleTrust = async (dev: DeviceRecord) => {
    const next = !dev.trusted
    try {
      await api.setTrusted(dev.mac, next)
      toast.success(next ? 'Marcado como de confianza' : 'Confianza retirada', {
        description: dev.hostname || dev.ip,
      })
      refresh()
    } catch (e) {
      toast.error('No se pudo cambiar la confianza', { description: (e as Error).message })
    }
  }

  const wake = async (dev: DeviceRecord) => {
    try {
      await api.wake(dev.mac)
      toast('Wake-on-LAN enviado', { description: dev.hostname || dev.ip })
    } catch (e) {
      toast.error('No se pudo enviar Wake-on-LAN', { description: (e as Error).message })
    }
  }

  const th = 'font-mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground'
  const SortHead = ({
    label,
    k,
    align = 'left',
    extra = '',
  }: {
    label: string
    k: SortKey
    align?: 'left' | 'right'
    extra?: string
  }) => {
    const active = sortKey === k
    const Icon = !active ? ChevronsUpDown : sortDir === 'asc' ? ArrowUp : ArrowDown
    return (
      <TableHead className={`${th} ${extra}`} aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
        <button
          onClick={() => toggleSort(k)}
          aria-label={`ordenar por ${label}${active ? (sortDir === 'asc' ? ', ascendente' : ', descendente') : ''}`}
          className={`press flex items-center gap-1 transition-colors hover:text-foreground ${align === 'right' ? 'ml-auto flex-row-reverse' : ''} ${active ? 'sort-active text-primary' : ''}`}
        >
          {label}
          <Icon className="h-3 w-3 shrink-0" strokeWidth={active ? 2.4 : 1.6} />
        </button>
      </TableHead>
    )
  }

  const emptyMsg =
    devices && devices.length > 0 ? 'ningún dispositivo coincide con el filtro' : 'sin dispositivos — lanza un scan'

  // A click-to-copy value (IP / MAC). Shows a cyan flash + check when copied.
  const CopyChip = ({ value, label, className = '' }: { value: string; label: string; className?: string }) => {
    const isCopied = copied === value
    return (
      <button
        type="button"
        onClick={() => copyValue(value, label)}
        title={`copiar ${label}`}
        aria-label={`copiar ${label} ${value}`}
        className={`copyable group/copy inline-flex items-center gap-1 ${isCopied ? 'copied-flash' : ''} ${className}`}
      >
        {value}
        {isCopied ? (
          <Check className="h-3 w-3 shrink-0 text-primary" strokeWidth={2.4} />
        ) : (
          <Copy className="h-3 w-3 shrink-0 opacity-0 transition-opacity group-hover/copy:opacity-60" strokeWidth={1.6} />
        )}
      </button>
    )
  }

  return (
    <>
      <GlassPanel
        title="Dispositivos"
        right={
          <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
            <span className="shrink-0 text-xs font-medium text-muted-foreground">{filtered.length} descubiertos</span>
            <Input
              placeholder="filtrar…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              aria-label="filtrar dispositivos"
              className="h-7 w-28 min-w-0 rounded-none border-border bg-secondary text-xs sm:w-40"
            />
          </div>
        }
        contentClassName="-mx-5 -mb-2"
      >
        <div className="px-5">
          <PanelError error={error} onRetry={refresh} />
        </div>

        {/* ── Desktop / tablet: sortable data table ───────────────────────── */}
        <div className="hidden max-h-[560px] overflow-auto px-5 pb-2 sm:block">
          <Table>
            <TableHeader className="[&_tr]:border-white/10">
              <TableRow className="border-white/10 hover:bg-transparent">
                <SortHead label="Host" k="host" />
                <SortHead label="IP / MAC" k="ip" />
                <SortHead label="Latencia" k="latency" align="right" />
                <SortHead label="Jitter" k="jitter" align="right" extra="hidden md:table-cell" />
                <SortHead label="Pérdida" k="loss" align="right" extra="hidden md:table-cell" />
                <SortHead label="Calidad" k="quality" />
                <TableHead className={`${th} hidden lg:table-cell`}>OS</TableHead>
                <TableHead className={th}>Puertos</TableHead>
                <TableHead className={th}>Trust</TableHead>
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
              {filtered.map((dev, i) => {
                const ports = portsOf(dev)
                return (
                  <TableRow
                    key={dev.mac}
                    style={{ '--row-i': Math.min(i, 12) } as React.CSSProperties}
                    className={`row-in border-white/[0.06] transition-colors hover:bg-white/[0.03] ${dev.online ? '' : 'opacity-45'}`}
                  >
                    <TableCell>
                      <button
                        onClick={() => setDetail(dev)}
                        title="Ver histórico"
                        className="flex items-center gap-2 text-left transition-colors hover:text-primary"
                      >
                        <span
                          aria-hidden="true"
                          className={`h-1.5 w-1.5 shrink-0 rounded-full ${dev.online ? 'bg-ok' : 'bg-muted-foreground/40'}`}
                        />
                        <span>
                          <span className="block font-semibold">{dev.hostname || dev.mdns_name || dev.ip}</span>
                          <span className="block text-xs text-muted-foreground">{dev.vendor || '—'}</span>
                        </span>
                      </button>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      <CopyChip value={dev.ip} label="IP" />
                      <br />
                      <CopyChip value={dev.mac} label="MAC" className="text-muted-foreground/70" />
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {dev.last_latency_ms != null ? (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger aria-label={`latencia ${dev.last_latency_ms} milisegundos`}>{dev.last_latency_ms}ms</TooltipTrigger>
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
                        <span className={lossColor(dev.packet_loss_pct)}>{dev.packet_loss_pct}%</span>
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
                              <TooltipTrigger aria-label={`puerto ${p.port} ${p.service}`}>
                                <span className="rounded-none border border-primary/40 bg-primary/[0.12] px-1.5 py-0.5 font-mono text-[11px] text-primary">
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
                          <span className="rounded-none border border-border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
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
                        className={`press flex h-5 w-5 items-center justify-center rounded-full border transition-colors ${
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
                          onClick={() => runSpeedtest(dev)}
                          disabled={testing.has(dev.mac)}
                          title="Speed test (latencia, jitter, pérdida, TCP)"
                          aria-label={`speed test de ${dev.ip}`}
                          className="press flex h-[26px] w-[26px] items-center justify-center rounded-none border border-border bg-secondary text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary disabled:opacity-50"
                        >
                          <Gauge className={`h-3.5 w-3.5 ${testing.has(dev.mac) ? 'animate-spin' : ''}`} strokeWidth={1.6} />
                        </button>
                        {!dev.online && (
                          <button
                            onClick={() => wake(dev)}
                            title="Wake-on-LAN"
                            aria-label={`despertar ${dev.ip} por Wake-on-LAN`}
                            className="press flex h-[26px] w-[26px] items-center justify-center rounded-none border border-border bg-secondary text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary"
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
                    {emptyMsg}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>

        {/* ── Mobile: stacked cards — every metric stays, nothing hidden ───── */}
        <div className="space-y-2 px-5 pb-3 sm:hidden">
          {loading && Array.from({ length: 4 }).map((_, i) => <Skeleton key={`mc-${i}`} className="h-24 w-full" />)}
          {!loading && filtered.length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">{emptyMsg}</p>
          )}
          {filtered.map((dev, i) => {
            const ports = portsOf(dev)
            return (
              <div
                key={dev.mac}
                style={{ '--row-i': Math.min(i, 12) } as React.CSSProperties}
                className={`row-in rounded-none border border-white/[0.08] bg-white/[0.02] p-3 ${dev.online ? '' : 'opacity-50'}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <button onClick={() => setDetail(dev)} className="flex min-w-0 items-center gap-2 text-left">
                    <span aria-hidden="true" className={`h-1.5 w-1.5 shrink-0 rounded-full ${dev.online ? 'bg-ok' : 'bg-muted-foreground/40'}`} />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold">{dev.hostname || dev.mdns_name || dev.ip}</span>
                      <span className="block font-mono text-xs text-muted-foreground">{dev.vendor || '—'}</span>
                    </span>
                  </button>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      onClick={() => toggleTrust(dev)}
                      aria-label={dev.trusted ? `quitar confianza de ${dev.ip}` : `marcar ${dev.ip} como de confianza`}
                      className={`press flex h-6 w-6 items-center justify-center rounded-full border ${dev.trusted ? 'border-ok/40 bg-ok/[0.16] text-ok' : 'border-destructive/40 bg-destructive/[0.16] text-destructive'}`}
                    >
                      {dev.trusted ? <ShieldCheck className="h-3 w-3" /> : <ShieldQuestion className="h-3 w-3" />}
                    </button>
                    <button
                      onClick={() => runSpeedtest(dev)}
                      disabled={testing.has(dev.mac)}
                      aria-label={`speed test de ${dev.ip}`}
                      className="press flex h-6 w-6 items-center justify-center rounded-none border border-border bg-secondary text-muted-foreground disabled:opacity-50"
                    >
                      <Gauge className={`h-3.5 w-3.5 ${testing.has(dev.mac) ? 'animate-spin' : ''}`} strokeWidth={1.6} />
                    </button>
                    {!dev.online && (
                      <button
                        onClick={() => wake(dev)}
                        aria-label={`despertar ${dev.ip} por Wake-on-LAN`}
                        className="press flex h-6 w-6 items-center justify-center rounded-none border border-border bg-secondary text-muted-foreground"
                      >
                        <Power className="h-3.5 w-3.5" strokeWidth={1.6} />
                      </button>
                    )}
                  </div>
                </div>
                <div className="mt-2 font-mono text-xs">
                  <CopyChip value={dev.ip} label="IP" />
                </div>
                <dl className="mt-3 grid grid-cols-4 gap-2 font-mono text-xs">
                  <div>
                    <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">Lat</dt>
                    <dd>{dev.last_latency_ms != null ? `${dev.last_latency_ms}ms` : '—'}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">Jitter</dt>
                    <dd className="text-muted-foreground">{dev.jitter_ms != null ? `${dev.jitter_ms}ms` : '—'}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">Pérdida</dt>
                    <dd className={dev.packet_loss_pct != null ? lossColor(dev.packet_loss_pct) : ''}>
                      {dev.packet_loss_pct != null ? `${dev.packet_loss_pct}%` : '—'}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">Calidad</dt>
                    <dd><QualityBadge score={dev.quality} /></dd>
                  </div>
                </dl>
                {ports.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {ports.slice(0, 8).map((p) => (
                      <span key={p.port} className="rounded-none border border-primary/40 bg-primary/[0.12] px-1.5 py-0.5 font-mono text-[11px] text-primary">
                        {p.port}
                      </span>
                    ))}
                    {ports.length > 8 && (
                      <span className="rounded-none border border-border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">+{ports.length - 8}</span>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </GlassPanel>
      {detail && (
        <Suspense fallback={null}>
          <DeviceDetailDialog device={detail} onClose={() => setDetail(null)} />
        </Suspense>
      )}
    </>
  )
}
