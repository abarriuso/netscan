import { GlassPanel, Meter } from '@/components/metrics'
import { formatBytes, formatUptime, usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import PanelError from './PanelError'

function StatLine({ label, value, valueClass }: { label: string; value: React.ReactNode; valueClass?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-white/[0.06] py-[7px] text-[12.5px] last:border-none">
      <span className="text-muted-foreground">{label}</span>
      <span className={`font-bold ${valueClass ?? ''}`}>{value}</span>
    </div>
  )
}

export default function Integrations() {
  const { data: pve, error: pveError } = usePoll(api.proxmox, 30000)
  const { data: tnas, error: tnasError } = usePoll(api.truenas, 30000)
  const { data: ag, error: agError } = usePoll(api.adguard, 30000)

  return (
    <div className="grid gap-[18px] lg:grid-cols-3">
      {/* Proxmox */}
      <GlassPanel title="Proxmox VE" meta={pve?.[0]?.name}>
        <PanelError error={pveError} />
        {(pve ?? []).length === 0 && !pveError && <p className="text-sm text-muted-foreground">sin instancias configuradas</p>}
        {(pve ?? []).map((inst) =>
          inst.error ? (
            <div key={inst.name} className="rounded-lg border border-destructive/40 p-3 text-xs">
              <span className="font-semibold">{inst.name}</span>
              <span className="ml-2 rounded-full bg-destructive px-2 py-0.5 text-[10px] font-bold text-white">error</span>
              <p className="mt-1 text-muted-foreground">{inst.error}</p>
            </div>
          ) : (
            <div key={inst.name} className="space-y-1.5">
              {(inst.guests ?? []).slice(0, 8).map((g) => (
                <div key={g.vmid} className="flex items-center justify-between py-1.5 text-[12.5px]">
                  <span className="flex items-center gap-2">
                    <span
                      className={`h-[7px] w-[7px] rounded-full ${g.status === 'running' ? 'bg-ok' : 'bg-muted-foreground/40'}`}
                      style={g.status === 'running' ? { boxShadow: '0 0 6px var(--ok, #34d399)' } : undefined}
                    />
                    {g.name ?? `${g.type}-${g.vmid}`}
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    {g.status === 'running' ? `running · ${g.maxcpu ?? '?'}c/${formatBytes(g.maxmem)}` : 'stopped'}
                  </span>
                </div>
              ))}
              <p className="pt-1 text-[11.5px] text-muted-foreground">
                {inst.guests_running}/{inst.guests_total} guests activos · v{inst.version}
              </p>
            </div>
          ),
        )}
      </GlassPanel>

      {/* TrueNAS */}
      <GlassPanel title="TrueNAS" meta={tnas?.[0]?.name}>
        <PanelError error={tnasError} />
        {(tnas ?? []).length === 0 && !tnasError && <p className="text-sm text-muted-foreground">sin instancias configuradas</p>}
        {(tnas ?? []).map((inst) =>
          inst.error ? (
            <div key={inst.name} className="rounded-lg border border-destructive/40 p-3 text-xs">
              <span className="font-semibold">{inst.name}</span>
              <span className="ml-2 rounded-full bg-destructive px-2 py-0.5 text-[10px] font-bold text-white">error</span>
              <p className="mt-1 text-muted-foreground">{inst.error}</p>
            </div>
          ) : (
            <div key={inst.name}>
              {(inst.pools ?? []).map((pool) => {
                const used = pool.size && pool.allocated ? Math.round((pool.allocated / pool.size) * 100) : 0
                return (
                  <div key={pool.name}>
                    <StatLine
                      label={`Pool: ${pool.name}`}
                      value={pool.status}
                      valueClass={pool.status === 'ONLINE' ? 'text-ok' : 'text-destructive'}
                    />
                    {pool.size ? (
                      <div className="pb-1">
                        <StatLine label="Capacidad usada" value={`${formatBytes(pool.allocated)} / ${formatBytes(pool.size)}`} />
                        <Meter percent={used} gradient="blue-teal" />
                      </div>
                    ) : null}
                  </div>
                )
              })}
              <StatLine label="Uptime" value={formatUptime(inst.uptime_seconds)} />
              <StatLine label="Cores" value={inst.cores} />
              <StatLine
                label="Pools OK"
                value={`${inst.pools_healthy}/${inst.pools_total}`}
                valueClass={inst.pools_healthy === inst.pools_total ? 'text-ok' : 'text-destructive'}
              />
              {(inst.alerts ?? []).length > 0 && (
                <StatLine label="Alertas del sistema" value={inst.alerts!.length} valueClass="text-destructive" />
              )}
            </div>
          ),
        )}
      </GlassPanel>

      {/* AdGuard */}
      <GlassPanel title="AdGuard Home" meta={ag?.[0]?.name}>
        <PanelError error={agError} />
        {(ag ?? []).length === 0 && !agError && <p className="text-sm text-muted-foreground">sin instancias configuradas</p>}
        {(ag ?? []).map((inst) =>
          inst.error ? (
            <div key={inst.name} className="rounded-lg border border-destructive/40 p-3 text-xs">
              <span className="font-semibold">{inst.name}</span>
              <span className="ml-2 rounded-full bg-destructive px-2 py-0.5 text-[10px] font-bold text-white">error</span>
              <p className="mt-1 text-muted-foreground">{inst.error}</p>
            </div>
          ) : (
            <div key={inst.name}>
              <StatLine label="Consultas hoy" value={(inst.num_dns_queries ?? 0).toLocaleString()} />
              <StatLine
                label="Bloqueadas"
                value={(inst.num_blocked_filtering ?? 0).toLocaleString()}
                valueClass="text-[color:var(--pink)]"
              />
              <div className="py-1">
                <Meter
                  percent={
                    inst.num_dns_queries ? ((inst.num_blocked_filtering ?? 0) / inst.num_dns_queries) * 100 : 0
                  }
                  gradient="pink-violet"
                />
              </div>
              <StatLine
                label="Tasa de bloqueo"
                value={`${inst.num_dns_queries ? (((inst.num_blocked_filtering ?? 0) / inst.num_dns_queries) * 100).toFixed(1) : '0.0'}%`}
              />
              <StatLine label="Tiempo medio" value={`${(inst.avg_processing_time ?? 0).toFixed(1)} ms`} />
              <StatLine label="Clientes" value={(inst.clients ?? []).length} />
            </div>
          ),
        )}
      </GlassPanel>
    </div>
  )
}
