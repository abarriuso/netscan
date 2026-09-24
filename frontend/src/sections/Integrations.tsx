import { useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import IntegrationFormDialog from '@/components/IntegrationFormDialog'
import { GlassPanel, Meter } from '@/components/metrics'
import { formatBytes, formatUptime, usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import type { IntegrationSetting } from '@/types'
import PanelError from './PanelError'
import { useI18n } from '@/i18n/context'

const KIND_LABELS: Record<string, string> = {
  proxmox: 'Proxmox VE',
  truenas: 'TrueNAS',
  adguard: 'AdGuard Home',
  pihole: 'Pi-hole',
}

function StatLine({ label, value, valueClass }: { label: string; value: React.ReactNode; valueClass?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-white/[0.06] py-[7px] text-[12.5px] last:border-none">
      <span className="text-muted-foreground">{label}</span>
      <span className={`font-bold ${valueClass ?? ''}`}>{value}</span>
    </div>
  )
}

/** Add/edit/remove Proxmox/TrueNAS/AdGuard/Pi-hole/custom instances from the
 *  dashboard — separate from the live-data cards below it, which just show
 *  whatever's currently configured (matching by name across the two would
 *  be fragile; this is the one clear place CRUD happens). */
function IntegrationManager({ onChanged }: { onChanged: () => void }) {
  const { t } = useI18n()
  const kindLabel = (kind: string) => (kind === 'custom' ? t('kindCustom') : (KIND_LABELS[kind] ?? kind))
  const { data: settings, error, refresh } = usePoll(api.listIntegrationSettings, 30000)
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<IntegrationSetting | null>(null)

  const openCreate = () => {
    setEditing(null)
    setFormOpen(true)
  }
  const openEdit = (item: IntegrationSetting) => {
    setEditing(item)
    setFormOpen(true)
  }
  const remove = async (item: IntegrationSetting) => {
    if (!item.id) return
    if (!window.confirm(t('confirmDelete', item.name))) return
    await api.deleteIntegration(item.id)
    refresh()
    onChanged()
  }
  const saved = () => {
    refresh()
    onChanged()
  }

  return (
    <GlassPanel
      title={t('integrationsTitle')}
      right={
        <button
          onClick={openCreate}
          className="flex items-center gap-1.5 rounded-none bg-primary px-3 py-1.5 font-mono text-xs font-bold uppercase tracking-wider text-primary-foreground shadow-hard-cyan transition-[filter,transform,box-shadow] hover:-translate-x-[1px] hover:-translate-y-[1px] hover:brightness-110"
        >
          <Plus className="h-3.5 w-3.5" />
          {t('add')}
        </button>
      }
    >
      <PanelError error={error} />
      {(settings ?? []).length === 0 && !error && (
        <p className="text-sm text-muted-foreground">
          {t('noIntegrations')}
        </p>
      )}
      <div className="space-y-1">
        {(settings ?? []).map((item, i) => (
          <div
            key={item.id ?? `config-${i}`}
            className="flex items-center justify-between gap-3 border-b border-white/[0.06] py-2 text-[12.5px] last:border-none"
          >
            <div className="flex min-w-0 items-center gap-2.5">
              <span
                className={`h-[7px] w-[7px] shrink-0 rounded-full ${item.enabled ? 'bg-ok' : 'bg-muted-foreground/40'}`}
              />
              <span className="truncate font-medium">{item.name}</span>
              <span className="shrink-0 rounded border border-white/10 px-1.5 py-0.5 font-mono text-[9.5px] text-muted-foreground">
                {kindLabel(item.kind)}
              </span>
              {!item.editable && (
                <span className="shrink-0 font-mono text-[9.5px] text-muted-foreground">{t('definedInConfig')}</span>
              )}
            </div>
            {item.editable && (
              <div className="flex shrink-0 items-center gap-1">
                <button
                  onClick={() => openEdit(item)}
                  aria-label={t('edit')}
                  title={t('edit')}
                  className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-white/10 hover:text-foreground"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => remove(item)}
                  aria-label={t('remove')}
                  title={t('remove')}
                  className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/20 hover:text-destructive"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      <IntegrationFormDialog open={formOpen} onOpenChange={setFormOpen} editing={editing} onSaved={saved} />
    </GlassPanel>
  )
}

export default function Integrations() {
  const { t } = useI18n()
  const { data: pve, error: pveError } = usePoll(api.proxmox, 30000)
  const { data: tnas, error: tnasError } = usePoll(api.truenas, 30000)
  const { data: ag, error: agError } = usePoll(api.adguard, 30000)
  const { data: ph, error: phError, refresh: refreshPihole } = usePoll(api.pihole, 30000)
  const { data: bookmarks, error: bookmarksError, refresh: refreshBookmarks } = usePoll(api.customBookmarks, 30000)

  const refreshAll = () => {
    refreshPihole()
    refreshBookmarks()
  }

  return (
    <div className="space-y-[18px]">
      <IntegrationManager onChanged={refreshAll} />

      <div className="grid gap-[18px] lg:grid-cols-2 xl:grid-cols-4">
        {/* Proxmox */}
        <GlassPanel title="Proxmox VE" meta={pve?.[0]?.name}>
          <PanelError error={pveError} />
          {(pve ?? []).length === 0 && !pveError && <p className="text-sm text-muted-foreground">{t('noInstances')}</p>}
          {(pve ?? []).map((inst) =>
            inst.error ? (
              <div key={inst.name} className="rounded-none border border-destructive/40 p-3 text-xs">
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
                <p className="pt-1 text-xs text-muted-foreground">
                  {t('guestsActive', inst.guests_running ?? 0, inst.guests_total ?? 0, String(inst.version ?? '?'))}
                </p>
              </div>
            ),
          )}
        </GlassPanel>

        {/* TrueNAS */}
        <GlassPanel title="TrueNAS" meta={tnas?.[0]?.name}>
          <PanelError error={tnasError} />
          {(tnas ?? []).length === 0 && !tnasError && <p className="text-sm text-muted-foreground">{t('noInstances')}</p>}
          {(tnas ?? []).map((inst) =>
            inst.error ? (
              <div key={inst.name} className="rounded-none border border-destructive/40 p-3 text-xs">
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
                          <StatLine label={t('usedCapacity')} value={`${formatBytes(pool.allocated)} / ${formatBytes(pool.size)}`} />
                          <Meter percent={used} gradient="sky" />
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
                  <StatLine label={t('systemAlerts')} value={inst.alerts!.length} valueClass="text-destructive" />
                )}
              </div>
            ),
          )}
        </GlassPanel>

        {/* AdGuard */}
        <GlassPanel title="AdGuard Home" meta={ag?.[0]?.name}>
          <PanelError error={agError} />
          {(ag ?? []).length === 0 && !agError && <p className="text-sm text-muted-foreground">{t('noInstances')}</p>}
          {(ag ?? []).map((inst) =>
            inst.error ? (
              <div key={inst.name} className="rounded-none border border-destructive/40 p-3 text-xs">
                <span className="font-semibold">{inst.name}</span>
                <span className="ml-2 rounded-full bg-destructive px-2 py-0.5 text-[10px] font-bold text-white">error</span>
                <p className="mt-1 text-muted-foreground">{inst.error}</p>
              </div>
            ) : (
              <div key={inst.name}>
                <StatLine label={t('queriesToday')} value={(inst.num_dns_queries ?? 0).toLocaleString()} />
                <StatLine
                  label={t('blocked')}
                  value={(inst.num_blocked_filtering ?? 0).toLocaleString()}
                  valueClass="text-[color:var(--pink)]"
                />
                <div className="py-1">
                  <Meter
                    percent={
                      inst.num_dns_queries ? ((inst.num_blocked_filtering ?? 0) / inst.num_dns_queries) * 100 : 0
                    }
                    gradient="teal"
                  />
                </div>
                <StatLine
                  label={t('blockRate')}
                  value={`${inst.num_dns_queries ? (((inst.num_blocked_filtering ?? 0) / inst.num_dns_queries) * 100).toFixed(1) : '0.0'}%`}
                />
                <StatLine label={t('avgTime')} value={`${(inst.avg_processing_time ?? 0).toFixed(1)} ms`} />
                <StatLine label={t('clients')} value={(inst.clients ?? []).length} />
              </div>
            ),
          )}
        </GlassPanel>

        {/* Pi-hole */}
        <GlassPanel title="Pi-hole" meta={ph?.[0]?.name}>
          <PanelError error={phError} />
          {(ph ?? []).length === 0 && !phError && <p className="text-sm text-muted-foreground">{t('noInstances')}</p>}
          {(ph ?? []).map((inst) =>
            inst.error ? (
              <div key={inst.name} className="rounded-none border border-destructive/40 p-3 text-xs">
                <span className="font-semibold">{inst.name}</span>
                <span className="ml-2 rounded-full bg-destructive px-2 py-0.5 text-[10px] font-bold text-white">error</span>
                <p className="mt-1 text-muted-foreground">{inst.error}</p>
              </div>
            ) : (
              <div key={inst.name}>
                <StatLine label={t('queriesToday')} value={(inst.num_dns_queries ?? 0).toLocaleString()} />
                <StatLine
                  label={t('blocked')}
                  value={(inst.num_blocked_filtering ?? 0).toLocaleString()}
                  valueClass="text-[color:var(--pink)]"
                />
                <div className="py-1">
                  <Meter percent={inst.percent_blocked ?? 0} gradient="teal" />
                </div>
                <StatLine label={t('blockRate')} value={`${(inst.percent_blocked ?? 0).toFixed(1)}%`} />
                <StatLine label={t('domainsListed')} value={(inst.domains_being_blocked ?? 0).toLocaleString()} />
                <StatLine label={t('clients')} value={inst.unique_clients ?? 0} />
              </div>
            ),
          )}
        </GlassPanel>
      </div>

      {/* Custom bookmarks */}
      {((bookmarks ?? []).length > 0 || bookmarksError) && (
        <GlassPanel title={t('linksTitle')} meta={t('bookmarks', (bookmarks ?? []).length)}>
          <PanelError error={bookmarksError} />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {(bookmarks ?? []).map((b) => (
              <a
                key={b.id}
                href={b.url}
                target="_blank"
                rel="noreferrer"
                className="flex flex-col items-center gap-2 rounded-none border border-border bg-secondary/60 p-3 text-center transition-colors hover:border-primary/50 hover:bg-secondary"
              >
                <div className="relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-none bg-white/10">
                  {b.logo_url ? (
                    <img src={b.logo_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <span className="font-mono text-xs font-bold text-muted-foreground">{b.name.slice(0, 2).toUpperCase()}</span>
                  )}
                  <span
                    className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-card ${b.status === 'up' ? 'bg-ok' : 'bg-destructive'}`}
                  />
                </div>
                <span className="truncate text-[11px] font-medium">{b.name}</span>
              </a>
            ))}
          </div>
        </GlassPanel>
      )}
    </div>
  )
}
