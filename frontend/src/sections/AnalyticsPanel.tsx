import { BarChart3 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import type { DeviceRecord, PortInfo } from '@/types'
import PanelError from './PanelError'

function Bar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 truncate text-right font-mono text-muted-foreground" title={label}>
        {label}
      </span>
      <div className="h-3.5 flex-1 overflow-hidden rounded-sm bg-muted/40">
        <div
          className={`h-full ${color}`}
          style={{ width: `${max > 0 ? Math.max((value / max) * 100, 4) : 0}%` }}
        />
      </div>
      <span className="w-8 font-mono font-semibold">{value}</span>
    </div>
  )
}

function portsOf(dev: DeviceRecord): PortInfo[] {
  try {
    return JSON.parse(dev.open_ports_json) as PortInfo[]
  } catch {
    return []
  }
}

export default function AnalyticsPanel({ refreshKey }: { refreshKey: number }) {
  const { data: devices, error } = usePoll(api.devices, 20000, refreshKey)

  const list = devices ?? []

  const vendors = new Map<string, number>()
  const oses = new Map<string, number>()
  const ports = new Map<string, number>()
  for (const dev of list) {
    if (dev.vendor) vendors.set(dev.vendor, (vendors.get(dev.vendor) ?? 0) + 1)
    if (dev.os_guess) oses.set(dev.os_guess, (oses.get(dev.os_guess) ?? 0) + 1)
    for (const p of portsOf(dev)) {
      const key = `${p.port} ${p.service}`
      ports.set(key, (ports.get(key) ?? 0) + 1)
    }
  }

  const top = (m: Map<string, number>, n: number) =>
    [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, n)
  const topVendors = top(vendors, 6)
  const topOS = top(oses, 5)
  const topPorts = top(ports, 8)
  const maxV = topVendors[0]?.[1] ?? 1
  const maxO = topOS[0]?.[1] ?? 1
  const maxP = topPorts[0]?.[1] ?? 1

  return (
    <Card className="bg-card/60">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 font-mono text-sm uppercase tracking-wider">
          <BarChart3 className="h-4 w-4 text-cyan-400" /> analítica de red
        </CardTitle>
      </CardHeader>
      <CardContent>
        <PanelError error={error} />
        {list.length === 0 ? (
          <p className="text-xs text-muted-foreground">sin datos — lanza un scan</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                vendors
              </p>
              {topVendors.map(([v, n]) => (
                <Bar key={v} label={v} value={n} max={maxV} color="bg-amber-400/70" />
              ))}
            </div>
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                sistemas operativos
              </p>
              {topOS.map(([v, n]) => (
                <Bar key={v} label={v || 'desconocido'} value={n} max={maxO} color="bg-violet-400/70" />
              ))}
            </div>
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                puertos más abiertos
              </p>
              {topPorts.map(([v, n]) => (
                <Bar key={v} label={v} value={n} max={maxP} color="bg-emerald-400/70" />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
