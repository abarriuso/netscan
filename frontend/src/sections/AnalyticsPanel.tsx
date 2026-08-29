import { GlassPanel } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import type { DeviceRecord, PortInfo } from '@/types'
import PanelError from './PanelError'

function MiniBars({ rows, max, gradient }: { rows: [string, number][]; max: number; gradient: string }) {
  return (
    <div className="flex flex-col gap-2.5">
      {rows.map(([label, value]) => (
        <div key={label} className="flex flex-col gap-1">
          <div className="flex items-center justify-between text-xs">
            <span className="truncate text-muted-foreground" title={label}>
              {label}
            </span>
            <span className="text-[11.5px] font-semibold text-muted-foreground/90">{value}</span>
          </div>
          <div className="h-[7px] overflow-hidden rounded-full bg-white/[0.07]">
            <div
              className="h-full rounded-full"
              style={{ width: `${max > 0 ? Math.max((value / max) * 100, 4) : 0}%`, background: gradient }}
            />
          </div>
        </div>
      ))}
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
      const key = `${p.port} · ${p.service}`
      ports.set(key, (ports.get(key) ?? 0) + 1)
    }
  }

  const top = (m: Map<string, number>, n: number) =>
    [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, n) as [string, number][]
  const topVendors = top(vendors, 5)
  const topOS = top(oses, 5)
  const topPorts = top(ports, 5)
  const maxV = topVendors[0]?.[1] ?? 1
  const maxO = topOS[0]?.[1] ?? 1
  const maxP = topPorts[0]?.[1] ?? 1

  if (list.length === 0) {
    return (
      <GlassPanel title="Analítica de red">
        <PanelError error={error} />
        <p className="text-sm text-muted-foreground">sin datos — lanza un scan</p>
      </GlassPanel>
    )
  }

  return (
    <div className="grid gap-[18px] lg:grid-cols-3">
      <GlassPanel title="Top vendors">
        <PanelError error={error} />
        <MiniBars rows={topVendors} max={maxV} gradient="linear-gradient(90deg, var(--violet-2), var(--violet))" />
      </GlassPanel>
      <GlassPanel title="Top sistemas operativos">
        <MiniBars rows={topOS} max={maxO} gradient="linear-gradient(90deg, #0d9488, var(--teal))" />
      </GlassPanel>
      <GlassPanel title="Top puertos abiertos">
        <MiniBars rows={topPorts} max={maxP} gradient="linear-gradient(90deg, #be185d, var(--pink))" />
      </GlassPanel>
    </div>
  )
}
