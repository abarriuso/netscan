import { Box, Database, HardDrive, ShieldHalf } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { formatBytes, formatUptime, usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'

export default function Integrations() {
  const { data: pve } = usePoll(api.proxmox, 30000)
  const { data: tnas } = usePoll(api.truenas, 30000)
  const { data: ag } = usePoll(api.adguard, 30000)

  return (
    <div className="grid gap-3 lg:grid-cols-3">
      {/* Proxmox */}
      <Card className="bg-card/60">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 font-mono text-sm uppercase tracking-wider">
            <Box className="h-4 w-4 text-orange-400" /> proxmox ve
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-xs">
          {(pve ?? []).length === 0 && <p className="text-muted-foreground">sin instancias configuradas</p>}
          {(pve ?? []).map((inst) =>
            inst.error ? (
              <div key={inst.name} className="rounded border border-red-900/50 p-2">
                <span className="font-mono font-semibold">{inst.name}</span>
                <Badge variant="destructive" className="ml-2 font-mono text-[10px]">error</Badge>
                <p className="mt-1 text-muted-foreground">{inst.error}</p>
              </div>
            ) : (
              <div key={inst.name} className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-semibold">{inst.name}</span>
                  <Badge variant="secondary" className="font-mono text-[10px]">v{inst.version}</Badge>
                </div>
                <p className="text-muted-foreground">
                  {inst.guests_running}/{inst.guests_total} guests activos
                </p>
                {(inst.guests ?? []).slice(0, 6).map((g) => (
                  <div key={g.vmid} className="flex items-center justify-between rounded bg-muted/40 px-2 py-1 font-mono">
                    <span className="flex items-center gap-2">
                      <span className={`h-1.5 w-1.5 rounded-full ${g.status === 'running' ? 'bg-emerald-400' : 'bg-zinc-600'}`} />
                      {g.name ?? `${g.type}-${g.vmid}`}
                    </span>
                    <span className="text-muted-foreground">
                      {g.type} · {g.maxcpu ?? '?'}c · {formatBytes(g.maxmem)}
                    </span>
                  </div>
                ))}
              </div>
            ),
          )}
        </CardContent>
      </Card>

      {/* TrueNAS */}
      <Card className="bg-card/60">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 font-mono text-sm uppercase tracking-wider">
            <Database className="h-4 w-4 text-sky-400" /> truenas
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-xs">
          {(tnas ?? []).length === 0 && <p className="text-muted-foreground">sin instancias configuradas</p>}
          {(tnas ?? []).map((inst) =>
            inst.error ? (
              <div key={inst.name} className="rounded border border-red-900/50 p-2">
                <span className="font-mono font-semibold">{inst.name}</span>
                <Badge variant="destructive" className="ml-2 font-mono text-[10px]">error</Badge>
                <p className="mt-1 text-muted-foreground">{inst.error}</p>
              </div>
            ) : (
              <div key={inst.name} className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-semibold">{inst.name}</span>
                  <Badge variant="secondary" className="font-mono text-[10px]">{inst.version}</Badge>
                </div>
                <p className="text-muted-foreground">
                  uptime {formatUptime(inst.uptime_seconds)} · {inst.cores} cores · pools {inst.pools_healthy}/{inst.pools_total} OK
                </p>
                {(inst.pools ?? []).map((pool) => {
                  const used = pool.size && pool.allocated ? Math.round((pool.allocated / pool.size) * 100) : 0
                  return (
                    <div key={pool.name} className="space-y-1 rounded bg-muted/40 px-2 py-1.5 font-mono">
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-2">
                          <HardDrive className="h-3 w-3" />
                          {pool.name}
                        </span>
                        <span className={pool.status === 'ONLINE' ? 'text-emerald-400' : 'text-red-400'}>
                          {pool.status}
                        </span>
                      </div>
                      {pool.size ? (
                        <>
                          <Progress value={used} className="h-1" />
                          <p className="text-[10px] text-muted-foreground">
                            {formatBytes(pool.allocated)} / {formatBytes(pool.size)} ({used}%)
                          </p>
                        </>
                      ) : null}
                    </div>
                  )
                })}
                {(inst.alerts ?? []).length > 0 && (
                  <Badge variant="destructive" className="font-mono text-[10px]">
                    {inst.alerts!.length} alertas del sistema
                  </Badge>
                )}
              </div>
            ),
          )}
        </CardContent>
      </Card>

      {/* AdGuard */}
      <Card className="bg-card/60">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 font-mono text-sm uppercase tracking-wider">
            <ShieldHalf className="h-4 w-4 text-violet-400" /> adguard home
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-xs">
          {(ag ?? []).length === 0 && <p className="text-muted-foreground">sin instancias configuradas</p>}
          {(ag ?? []).map((inst) =>
            inst.error ? (
              <div key={inst.name} className="rounded border border-red-900/50 p-2">
                <span className="font-mono font-semibold">{inst.name}</span>
                <Badge variant="destructive" className="ml-2 font-mono text-[10px]">error</Badge>
                <p className="mt-1 text-muted-foreground">{inst.error}</p>
              </div>
            ) : (
              <div key={inst.name} className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-semibold">{inst.name}</span>
                  <Badge variant="secondary" className="font-mono text-[10px]">{inst.version}</Badge>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="rounded bg-muted/40 p-2 text-center">
                    <div className="font-mono text-lg font-bold">{(inst.num_dns_queries ?? 0).toLocaleString()}</div>
                    <div className="text-[10px] uppercase text-muted-foreground">consultas DNS</div>
                  </div>
                  <div className="rounded bg-muted/40 p-2 text-center">
                    <div className="font-mono text-lg font-bold text-violet-300">
                      {(inst.num_blocked_filtering ?? 0).toLocaleString()}
                    </div>
                    <div className="text-[10px] uppercase text-muted-foreground">bloqueadas</div>
                  </div>
                </div>
                <p className="text-muted-foreground">
                  {(inst.clients ?? []).length} clientes · {(inst.avg_processing_time ?? 0).toFixed(1)}ms media
                </p>
              </div>
            ),
          )}
        </CardContent>
      </Card>
    </div>
  )
}
