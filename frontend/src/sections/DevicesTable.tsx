import { useMemo, useState } from 'react'
import { ShieldCheck, ShieldQuestion } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
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

function portsOf(dev: DeviceRecord): PortInfo[] {
  try {
    return JSON.parse(dev.open_ports_json) as PortInfo[]
  } catch {
    return []
  }
}

export default function DevicesTable({ refreshKey }: { refreshKey: number }) {
  const { data: devices, refresh } = usePoll(api.devices, 15000)
  const [filter, setFilter] = useState('')
  void refreshKey

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
    <Card className="bg-card/60">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="font-mono text-sm uppercase tracking-wider">
          dispositivos ({filtered.length})
        </CardTitle>
        <Input
          placeholder="filtrar por ip, mac, hostname, vendor…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="h-8 w-72 font-mono text-xs"
        />
      </CardHeader>
      <CardContent className="p-0">
        <div className="max-h-[520px] overflow-auto">
          <Table>
            <TableHeader className="sticky top-0 bg-card">
              <TableRow>
                <TableHead className="w-8"></TableHead>
                <TableHead>IP</TableHead>
                <TableHead>MAC</TableHead>
                <TableHead>Nombre</TableHead>
                <TableHead>Vendor</TableHead>
                <TableHead className="text-right">Latencia</TableHead>
                <TableHead>OS</TableHead>
                <TableHead>Puertos</TableHead>
                <TableHead className="w-10"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((dev) => {
                const ports = portsOf(dev)
                return (
                  <TableRow key={dev.mac} className={dev.online ? '' : 'opacity-40'}>
                    <TableCell>
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${
                          dev.online ? 'bg-emerald-400' : 'bg-zinc-600'
                        }`}
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs font-semibold">{dev.ip}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{dev.mac}</TableCell>
                    <TableCell className="text-xs">
                      {dev.hostname || dev.mdns_name || <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell className="max-w-40 truncate text-xs">{dev.vendor || '—'}</TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {dev.last_latency_ms != null ? `${dev.last_latency_ms}ms` : '—'}
                    </TableCell>
                    <TableCell>
                      {dev.os_guess ? (
                        <Badge variant="secondary" className="font-mono text-[10px]">
                          {dev.os_guess}
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="max-w-64">
                      <div className="flex flex-wrap gap-1">
                        {ports.slice(0, 8).map((p) => (
                          <TooltipProvider key={p.port}>
                            <Tooltip>
                              <TooltipTrigger>
                                <Badge variant="outline" className="font-mono text-[10px]">
                                  {p.port}
                                </Badge>
                              </TooltipTrigger>
                              <TooltipContent className="font-mono text-xs">
                                {p.service}
                                {p.version ? ` — ${p.version}` : ''}
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        ))}
                        {ports.length > 8 && (
                          <Badge variant="outline" className="font-mono text-[10px]">
                            +{ports.length - 8}
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <button onClick={() => toggleTrust(dev)} title={dev.trusted ? 'verificado' : 'marcar como de confianza'}>
                        {dev.trusted ? (
                          <ShieldCheck className="h-4 w-4 text-emerald-400" />
                        ) : (
                          <ShieldQuestion className="h-4 w-4 text-amber-400" />
                        )}
                      </button>
                    </TableCell>
                  </TableRow>
                )
              })}
              {filtered.length === 0 && (
                <TableRow>
                  <TableCell colSpan={9} className="py-8 text-center text-sm text-muted-foreground">
                    sin dispositivos — lanza un scan
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
