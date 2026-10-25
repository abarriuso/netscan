import { useState } from 'react'
import { AlertTriangle, Check, CheckCheck, DoorOpen, ShieldAlert, ShieldQuestion, Sparkle, TrendingDown, TrendingUp } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { GlassPanel } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import { openDeviceDetail } from '@/lib/deviceDetail'
import { fmtAgo } from '@/lib/format'
import PanelError from './PanelError'
import { useI18n } from '@/i18n/context'

const KIND_STYLE: Record<string, { icon: typeof Sparkle; iconClass: string }> = {
  new_device: { icon: Sparkle, iconClass: 'bg-primary/[0.16] text-primary' },
  mac_changed: { icon: ShieldQuestion, iconClass: 'bg-[color:var(--teal)]/[0.16] text-[color:var(--teal)]' },
  device_down: { icon: TrendingDown, iconClass: 'bg-destructive/[0.16] text-destructive' },
  device_back: { icon: TrendingUp, iconClass: 'bg-ok/[0.16] text-ok' },
  ports_changed: { icon: DoorOpen, iconClass: 'bg-warn/[0.16] text-warn' },
  ip_conflict: { icon: AlertTriangle, iconClass: 'bg-destructive/[0.16] text-destructive' },
  gateway_mac_changed: { icon: ShieldAlert, iconClass: 'bg-destructive/[0.22] text-destructive' },
}

export default function AlertsFeed({ refreshKey }: { refreshKey: number }) {
  const { t, locale } = useI18n()
  const [unreadOnly, setUnreadOnly] = useState(false)
  const { data: alerts, error, refresh } = usePoll(() => api.alerts(unreadOnly), 15000, refreshKey + (unreadOnly ? 0.5 : 0))

  const ack = async (id: number) => {
    await api.ackAlert(id)
    refresh()
  }
  const ackAll = async () => {
    try {
      const r = await api.ackAllAlerts()
      toast.success(t('ackAllDone', r.acknowledged))
      refresh()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  const list = alerts ?? []
  const unread = list.filter((a) => !a.acknowledged).length

  return (
    <GlassPanel
      title={t('alertsTitle')}
      right={
        <div className="flex items-center gap-2 font-mono text-[10.5px]">
          <span className="uppercase tracking-wider text-muted-foreground">{t('alertsRecent', list.length)}</span>
          <button
            onClick={() => setUnreadOnly((v) => !v)}
            className={`border px-2 py-0.5 uppercase tracking-wider ${unreadOnly ? 'border-primary/60 bg-primary/[0.12] text-primary' : 'border-border text-muted-foreground hover:text-foreground'}`}
          >
            {t('unreadOnly')}
          </button>
          {unread > 0 && (
            <button
              onClick={ackAll}
              title={t('ackAll')}
              className="flex items-center gap-1 border border-border px-2 py-0.5 uppercase tracking-wider text-muted-foreground hover:border-primary/60 hover:text-primary"
            >
              <CheckCheck className="h-3 w-3" /> {t('ackAll')}
            </button>
          )}
        </div>
      }
    >
      <PanelError error={error} onRetry={refresh} />
      {list.length === 0 && <p className="text-sm text-muted-foreground">{t('allQuietHere')}</p>}
      <div className="max-h-[460px] divide-y divide-white/[0.06] overflow-y-auto pr-1">
        {list.slice(0, 50).map((alert) => {
          const style = KIND_STYLE[alert.kind] ?? KIND_STYLE.new_device
          const Icon = style.icon
          return (
            <div key={alert.id} className={`flex items-start gap-3 py-3 ${alert.acknowledged ? 'opacity-40' : ''}`}>
              <div className={`flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] ${style.iconClass}`}>
                <Icon className="h-3.5 w-3.5" />
              </div>
              <button
                type="button"
                className="min-w-0 flex-1 text-left"
                onClick={() => alert.device_mac && openDeviceDetail(alert.device_mac)}
                title={alert.detail}
              >
                <p className="flex items-center gap-2 text-[13px] font-semibold">
                  {t('alertKind', alert.kind)}
                  {alert.device_ip ? ` · ${alert.device_ip}` : ''}
                  {!alert.acknowledged && (
                    <span className="rounded-full border border-warn/35 bg-warn/[0.14] px-2 py-0.5 text-[10px] font-bold text-warn">
                      {t('unread')}
                    </span>
                  )}
                </p>
                {/* The server's own detail (old IP, ports opened, MACs...)
                    is the evidence — shown, not hidden behind a hover. */}
                <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">{alert.detail}</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground/70">{new Date(alert.created_at).toLocaleString(locale)}</p>
              </button>
              <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{fmtAgo(alert.created_at)}</span>
              {!alert.acknowledged && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 shrink-0 p-0 text-muted-foreground hover:text-foreground"
                  onClick={() => ack(alert.id)}
                  aria-label={t('markRead')}
                >
                  <Check className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
          )
        })}
      </div>
    </GlassPanel>
  )
}
