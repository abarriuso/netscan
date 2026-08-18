import { Activity, Radar, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { useScanProgress } from '@/hooks/useNetscan'

const STAGE_LABELS: Record<string, string> = {
  idle: 'en espera',
  arp: 'descubrimiento ARP',
  mdns: 'mDNS / Bonjour',
  enrich: 'enriqueciendo dispositivos',
  done: 'completado',
}

export default function Header({ onScanDone }: { onScanDone: () => void }) {
  const { progress, scanning, startScan } = useScanProgress()
  const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0

  if (progress.stage === 'done') onScanDone()

  const label = progress.stage.startsWith('error')
    ? progress.stage
    : STAGE_LABELS[progress.stage] ?? progress.stage

  return (
    <header className="flex flex-wrap items-center gap-4 border-b border-border px-6 py-4">
      <div className="flex items-center gap-3">
        <Radar className="h-6 w-6 text-emerald-400" />
        <div>
          <h1 className="font-mono text-lg font-bold tracking-tight">NETSCAN</h1>
          <p className="text-xs text-muted-foreground">homelab network &amp; systems monitor</p>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-4">
        {scanning && (
          <div className="flex w-64 flex-col gap-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span className="flex items-center gap-1">
                <Activity className="h-3 w-3 animate-pulse text-emerald-400" />
                {label}
              </span>
              <span className="font-mono">{pct}%</span>
            </div>
            <Progress value={pct} className="h-1.5" />
          </div>
        )}
        {progress.stage.startsWith('error') && (
          <Badge variant="destructive" className="font-mono text-xs">{progress.stage}</Badge>
        )}
        <Button
          size="sm"
          variant="outline"
          disabled={scanning}
          onClick={() => startScan(false)}
          className="font-mono"
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${scanning ? 'animate-spin' : ''}`} />
          scan rápido
        </Button>
        <Button size="sm" disabled={scanning} onClick={() => startScan(true)} className="font-mono">
          <Radar className="mr-2 h-4 w-4" />
          scan completo
        </Button>
      </div>
    </header>
  )
}
