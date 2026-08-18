import { BellRing, Clock3, MonitorCheck, ShieldAlert } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import PanelError from './PanelError'

function Stat({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: typeof MonitorCheck
  label: string
  value: string | number
  accent: string
}) {
  return (
    <Card className="bg-card/60">
      <CardContent className="flex items-center gap-4 p-4">
        <Icon className={`h-8 w-8 ${accent}`} />
        <div>
          <div className="font-mono text-2xl font-bold leading-none">{value}</div>
          <div className="mt-1 text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
        </div>
      </CardContent>
    </Card>
  )
}

export default function StatCards({ refreshKey }: { refreshKey: number }) {
  const { data, error } = usePoll(api.overview, 15000, refreshKey)

  return (
    <div className="space-y-2">
      <PanelError error={error} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat icon={MonitorCheck} label="online / total" value={`${data?.devices_online ?? 0} / ${data?.devices_total ?? 0}`} accent="text-emerald-400" />
        <Stat icon={ShieldAlert} label="sin verificar" value={data?.devices_untrusted ?? 0} accent="text-amber-400" />
        <Stat icon={BellRing} label="alertas" value={data?.alerts_unacknowledged ?? 0} accent="text-red-400" />
        <Stat
          icon={Clock3}
          label="último scan"
          value={data?.last_scan ? new Date(data.last_scan).toLocaleTimeString() : 'nunca'}
          accent="text-sky-400"
        />
      </div>
    </div>
  )
}
