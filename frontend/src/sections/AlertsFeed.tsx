import { BellRing, Check } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import PanelError from './PanelError'

const KIND_STYLES: Record<string, { label: string; variant: 'destructive' | 'secondary' | 'outline' }> = {
  new_device: { label: 'nuevo', variant: 'destructive' },
  mac_changed: { label: 'ip cambiada', variant: 'secondary' },
  device_down: { label: 'caído', variant: 'destructive' },
  device_back: { label: 'recuperado', variant: 'outline' },
}

export default function AlertsFeed({ refreshKey }: { refreshKey: number }) {
  const { data: alerts, error, refresh } = usePoll(() => api.alerts(false), 15000, refreshKey)

  const ack = async (id: number) => {
    await api.ackAlert(id)
    refresh()
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 font-mono text-sm uppercase tracking-wider">
          <BellRing className="h-4 w-4 text-muted-foreground" strokeWidth={1.6} /> alertas
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs">
        <PanelError error={error} />
        {(alerts ?? []).length === 0 && (
          <p className="text-muted-foreground">todo tranquilo por aquí</p>
        )}
        {(alerts ?? []).slice(0, 12).map((alert) => {
          const style = KIND_STYLES[alert.kind] ?? KIND_STYLES.new_device
          return (
            <div
              key={alert.id}
              className={`flex items-center gap-3 rounded border border-border/60 px-3 py-2 ${
                alert.acknowledged ? 'opacity-40' : ''
              }`}
            >
              <Badge variant={style.variant} className="font-mono text-[10px]">
                {style.label}
              </Badge>
              <div className="min-w-0 flex-1">
                <p className="truncate">{alert.detail}</p>
                <p className="font-mono text-[10px] text-muted-foreground">
                  {new Date(alert.created_at).toLocaleString()}
                </p>
              </div>
              {!alert.acknowledged && (
                <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => ack(alert.id)} aria-label="marcar alerta como leída">
                  <Check className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
