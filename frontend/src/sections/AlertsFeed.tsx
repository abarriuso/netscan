import { Check, ShieldQuestion, Sparkle, TrendingDown, TrendingUp } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { GlassPanel } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import PanelError from './PanelError'

const KIND_STYLE: Record<string, { icon: typeof Sparkle; iconClass: string }> = {
  new_device: { icon: Sparkle, iconClass: 'bg-primary/[0.16] text-[#c4b5fd]' },
  mac_changed: { icon: ShieldQuestion, iconClass: 'bg-[color:var(--teal)]/[0.16] text-[color:var(--teal)]' },
  device_down: { icon: TrendingDown, iconClass: 'bg-destructive/[0.16] text-destructive' },
  device_back: { icon: TrendingUp, iconClass: 'bg-ok/[0.16] text-ok' },
}

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${Math.round(s)}s`
  if (s < 3600) return `${Math.round(s / 60)}m`
  if (s < 86400) return `${Math.round(s / 3600)}h`
  return `${Math.round(s / 86400)}d`
}

export default function AlertsFeed({ refreshKey }: { refreshKey: number }) {
  const { data: alerts, error, refresh } = usePoll(() => api.alerts(false), 15000, refreshKey)

  const ack = async (id: number) => {
    await api.ackAlert(id)
    refresh()
  }

  const list = alerts ?? []

  return (
    <GlassPanel title="Alertas" meta={`${list.length} recientes`}>
      <PanelError error={error} />
      {list.length === 0 && <p className="text-sm text-muted-foreground">todo tranquilo por aquí</p>}
      <div className="divide-y divide-white/[0.06]">
        {list.slice(0, 12).map((alert) => {
          const style = KIND_STYLE[alert.kind] ?? KIND_STYLE.new_device
          const Icon = style.icon
          return (
            <div key={alert.id} className={`flex items-start gap-3 py-3 ${alert.acknowledged ? 'opacity-40' : ''}`}>
              <div className={`flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] ${style.iconClass}`}>
                <Icon className="h-3.5 w-3.5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 text-[13px] font-semibold">
                  {alert.detail}
                  {!alert.acknowledged && (
                    <span className="rounded-full border border-warn/35 bg-warn/[0.14] px-2 py-0.5 text-[10px] font-bold text-warn">
                      sin leer
                    </span>
                  )}
                </p>
                <p className="mt-0.5 text-[11.5px] text-muted-foreground">
                  {new Date(alert.created_at).toLocaleString()}
                </p>
              </div>
              <span className="shrink-0 text-[11px] text-muted-foreground">{timeAgo(alert.created_at)}</span>
              {!alert.acknowledged && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 shrink-0 p-0 text-muted-foreground hover:text-foreground"
                  onClick={() => ack(alert.id)}
                  aria-label="marcar alerta como leída"
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
