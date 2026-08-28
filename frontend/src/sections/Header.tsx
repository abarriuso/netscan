import { useEffect } from 'react'
import { Activity, ChevronDown, Play, Radar } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Kbd } from '@/components/ui/kbd'
import { usePoll, useScanProgress } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import type { ScanStage } from '@/types'

const STAGE_LABELS: Record<string, string> = {
  idle: 'en espera',
  arp: 'descubrimiento ARP',
  mdns: 'mDNS / Bonjour',
  nmap: 'nmap — puertos y versión',
  rustscan: 'RustScan — descubrimiento de puertos',
  nuclei: 'auditoría nuclei',
  whatweb: 'huella web (whatweb)',
  testssl: 'auditoría TLS (testssl.sh)',
  enrich: 'puertos · versiones · fingerprint',
  done: 'completado',
}

interface ToolAction {
  stage?: ScanStage
  full?: boolean
  name: string
  description: string
  /** Key into capabilities.tools (or "mdns") that gates availability. */
  requires?: string
  shortcut?: string
}

const SCANS: ToolAction[] = [
  {
    full: false,
    name: 'escaneo rápido',
    description: 'ARP + resolución de hostname. Unos segundos.',
    shortcut: 'R',
  },
  {
    full: true,
    name: 'escaneo completo',
    description: 'Puertos, fingerprint, mDNS y nuclei si están instalados. Varios minutos.',
    shortcut: 'F',
  },
]

const TOOLS: ToolAction[] = [
  {
    stage: 'arp',
    name: 'descubrimiento ARP',
    description: 'Barrido ARP puro de la red local, sin enriquecer.',
  },
  {
    stage: 'mdns',
    name: 'mDNS / Bonjour',
    description: 'Nombra dispositivos IoT que no responden a DNS inverso.',
    requires: 'mdns',
  },
  {
    stage: 'nmap',
    name: 'nmap',
    description: 'Versión real de cada servicio abierto (-sV).',
    requires: 'nmap',
  },
  {
    stage: 'rustscan',
    name: 'rustscan',
    description: 'Descubrimiento de puertos ultrarrápido; alimenta a nmap.',
    requires: 'rustscan',
  },
  {
    stage: 'nuclei',
    name: 'nuclei',
    description: 'Auditoría de vulnerabilidades por plantillas, contra las web UI encontradas.',
    requires: 'nuclei',
  },
  {
    stage: 'whatweb',
    name: 'whatweb',
    description: 'Huella de tecnologías web (servidor, framework, CMS) de cada web UI encontrada.',
    requires: 'whatweb',
  },
  {
    stage: 'testssl',
    name: 'testssl.sh',
    description: 'Auditoría de configuración TLS de cada web UI con HTTPS. Lento — solo Linux/WSL.',
    requires: 'testssl',
  },
]

export default function Header({ onScanDone }: { onScanDone: () => void }) {
  const { progress, scanning, startScan } = useScanProgress()
  const { data: caps } = usePoll(api.capabilities, 60000)
  const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0

  useEffect(() => {
    if (progress.stage === 'done') onScanDone()
  }, [progress.stage, onScanDone])

  const label = progress.stage.startsWith('error')
    ? progress.stage
    : (STAGE_LABELS[progress.stage] ?? progress.stage)

  const isAvailable = (requires?: string) => {
    if (!requires) return true
    if (requires === 'mdns') return caps?.capabilities.mdns ?? true
    return caps?.tools[requires]?.available ?? true
  }

  const run = (action: ToolAction) => startScan({ full: action.full, only: action.stage })

  return (
    <header className="flex flex-wrap items-end gap-6 border-b border-border bg-card/40 px-8 py-5">
      <div className="flex items-center gap-3">
        <Radar className="h-6 w-6 text-foreground" strokeWidth={1.4} />
        <div className="border-b-2 border-primary pb-1.5">
          <h1 className="text-xl font-semibold tracking-tight">Netscan</h1>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
            monitor de red y sistemas para homelab
          </p>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-4">
        {(scanning || progress.stage.startsWith('error')) && (
          <div className="flex w-72 flex-col gap-1">
            <div className="flex items-center justify-between font-mono text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5 truncate">
                {progress.stage.startsWith('error') ? (
                  <Badge variant="destructive" className="font-mono text-xs">
                    {progress.stage}
                  </Badge>
                ) : (
                  <>
                    <Activity className="h-3 w-3 animate-pulse" />
                    {label}
                    <span className="text-[10px]">
                      {progress.done}/{progress.total}
                    </span>
                  </>
                )}
              </span>
              <span>{pct}%</span>
            </div>
            <Progress value={pct} className="h-1" />
          </div>
        )}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="outline" disabled={scanning} className="font-mono lowercase">
              acciones
              <ChevronDown className="ml-1 h-3.5 w-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-96">
            <DropdownMenuLabel className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              escaneos
            </DropdownMenuLabel>
            {SCANS.map((action) => (
              <DropdownMenuItem
                key={action.name}
                onSelect={() => run(action)}
                className="items-start gap-3 py-2.5"
              >
                <Play className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-sm font-medium lowercase">{action.name}</div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {action.description}
                  </p>
                </div>
                {action.shortcut && (
                  <DropdownMenuShortcut>
                    <Kbd>{action.shortcut}</Kbd>
                  </DropdownMenuShortcut>
                )}
              </DropdownMenuItem>
            ))}

            <DropdownMenuSeparator />
            <DropdownMenuLabel className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              herramientas individuales
            </DropdownMenuLabel>
            {TOOLS.map((action) => {
              const available = isAvailable(action.requires)
              return (
                <DropdownMenuItem
                  key={action.name}
                  disabled={!available}
                  onSelect={() => run(action)}
                  className="items-start gap-3 py-2.5"
                >
                  <Play className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="font-mono text-sm font-medium lowercase">{action.name}</div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {action.description}
                    </p>
                  </div>
                  {!available && (
                    <span className="shrink-0 rounded border border-border px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
                      no instalado
                    </span>
                  )}
                </DropdownMenuItem>
              )
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
