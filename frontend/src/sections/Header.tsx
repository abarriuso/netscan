import { useEffect } from 'react'
import { Activity, ChevronDown, Play } from 'lucide-react'
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
  const { data: caps, error: capsError } = usePoll(api.capabilities, 60000)
  const connected = !capsError
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
    <header className="glass flex flex-wrap items-center justify-between gap-4 px-6 py-3.5">
      <div className="flex items-center gap-3">
        <div
          className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-[10px] text-[16px] font-extrabold text-[#05040a] shadow-[0_0_24px_rgba(139,92,246,0.5)]"
          style={{ background: 'linear-gradient(135deg, var(--violet), var(--teal))' }}
        >
          NS
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-[19px] font-extrabold tracking-tight">NetScan</span>
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Homelab Monitor
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {(scanning || progress.stage.startsWith('error')) && (
          <div className="flex w-72 flex-col gap-1">
            <div className="flex items-center justify-between font-mono text-xs text-muted-foreground">
              <span className="flex min-w-0 items-center gap-1.5">
                {progress.stage.startsWith('error') ? (
                  <Badge variant="destructive" className="min-w-0 truncate font-mono text-xs">
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

        <span
          className={`flex items-center gap-2 rounded-full border px-3.5 py-2 text-[12.5px] font-semibold ${
            connected
              ? 'border-ok/35 bg-ok/10 text-ok'
              : 'border-destructive/35 bg-destructive/10 text-destructive'
          }`}
        >
          <span
            className={`h-[7px] w-[7px] rounded-full bg-current ${connected ? 'animate-pulse' : ''}`}
            style={{ boxShadow: '0 0 8px currentColor' }}
          />
          {connected ? 'Live — conectado' : 'Sin conexión'}
        </span>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              disabled={scanning}
              className="flex items-center gap-2 rounded-[10px] px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-[0_4px_20px_rgba(109,40,217,0.45)] transition-[filter,transform] duration-150 hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:hover:brightness-100"
              style={{ background: 'linear-gradient(135deg, var(--violet), var(--blue))' }}
            >
              <Play className="h-3.5 w-3.5" />
              Ejecutar scan
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="w-96 border-white/[0.12] bg-[#141021]/90 text-foreground shadow-2xl backdrop-blur-xl backdrop-saturate-150"
          >
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
