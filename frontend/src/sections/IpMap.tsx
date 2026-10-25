import { GlassPanel, Meter } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import { openDeviceDetail } from '@/lib/deviceDetail'
import { fmtDateTime } from '@/lib/format'
import type { IpState } from '@/types'
import PanelError from './PanelError'
import { useI18n } from '@/i18n/context'

const CELL: Record<IpState, string> = {
  network: 'bg-white/[0.04] text-muted-foreground/40',
  broadcast: 'bg-white/[0.04] text-muted-foreground/40',
  gateway: 'bg-primary/80 text-primary-foreground',
  self: 'bg-[color:var(--accent-magenta)]/80 text-white',
  online: 'bg-ok/70 text-[#04130c]',
  offline: 'bg-warn/45 text-[#1c1406]',
  free: 'bg-white/[0.03] text-muted-foreground/45 hover:bg-white/[0.08]',
}

/** IPAM view of the subnet: every address, used/free, with the device
 *  behind it — what to pick for a new static IP, how full the range is. */
export default function IpMap() {
  const { t, locale } = useI18n()
  const { data, error, refresh } = usePoll(() => api.ipMap(), 30000)
  const cols = data && data.size > 256 ? 32 : 16

  return (
    <GlassPanel
      title={t('ipmapTitle')}
      meta={data ? t('ipmapMeta', data.network, data.used, data.usable) : undefined}
    >
      <PanelError error={error} onRetry={refresh} />
      {data && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[11px]">
            <div className="w-64">
              <Meter percent={data.utilization_pct} label={t('ipmapUtil')} value={`${data.utilization_pct.toFixed(1)} %`} />
            </div>
            {(['gateway', 'self', 'online', 'offline', 'free'] as IpState[]).map((s) => (
              <span key={s} className="flex items-center gap-1.5">
                <span className={`inline-block h-3 w-3 ${CELL[s].split(' ')[0]}`} />
                {t('ipState', s)} <span className="text-muted-foreground">{data.counts[s] ?? 0}</span>
              </span>
            ))}
          </div>
          <div className="grid gap-[3px]" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
            {data.cells.map((c) => {
              const octet = c.ip.split('.').pop()
              const clickable = !!c.mac
              return (
                <button
                  key={c.ip}
                  type="button"
                  disabled={!clickable}
                  onClick={() => clickable && openDeviceDetail(c.mac)}
                  title={`${c.ip} · ${t('ipState', c.state)}${c.name ? ` · ${c.name}` : ''}${c.mac ? ` · ${c.mac}` : ''}${c.last_seen ? ` · ${t('ipmapLastSeen', fmtDateTime(c.last_seen, locale))}` : ''}`}
                  className={`flex aspect-square items-center justify-center font-mono text-[9.5px] font-semibold tabular-nums transition-[filter] ${CELL[c.state]} ${clickable ? 'cursor-pointer hover:brightness-125' : 'cursor-default'}`}
                >
                  {octet}
                </button>
              )
            })}
          </div>
        </>
      )}
    </GlassPanel>
  )
}
