import { useEffect } from 'react'
import { Activity, ChevronDown, KeyRound, Play } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
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
import { toast } from 'sonner'
import { usePoll, useScanProgress } from '@/hooks/useNetscan'
import { api, requestTokenDialog } from '@/lib/api'
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

const fmtElapsed = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export default function Header({ onScanDone }: { onScanDone: () => void }) {
  const { progress, scanning, elapsed, wsConnected, startScan } = useScanProgress()
  const { data: caps, error: capsError } = usePoll(api.capabilities, 60000)
  const connected = !capsError
  const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0
  // A scan is running but the live socket is down: we're on the HTTP fallback
  // poll (slower updates). Tell the user instead of looking frozen/healthy.
  const degraded = scanning && !wsConnected && !progress.stage.startsWith('error')

  useEffect(() => {
    if (progress.stage === 'done') {
      onScanDone()
      toast.success('Escaneo completado')
    } else if (progress.stage.startsWith('error')) {
      toast.error('Error en el escaneo', { description: progress.stage })
    }
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
    <header className="glass hud flex flex-wrap items-center justify-between gap-4 px-6 py-3.5">
      <div className="flex items-center gap-3">
        <div
          role="img"
          aria-label="NetScan"
          className="flex h-[40px] w-[40px] shrink-0 items-center justify-center rounded-none border-2 font-mono text-[15px] font-bold leading-[0.85] tracking-tight"
          style={{
            background: 'rgba(45,226,230,0.08)',
            borderColor: 'rgba(45,226,230,0.5)',
            color: 'var(--accent-cyan)',
            textAlign: 'center',
            boxShadow: '3px 3px 0 0 rgba(45,226,230,0.15)',
          }}
        >
          ◜◝
          <br />
          ◟◞
        </div>
        <div className="flex flex-col leading-tight">
          <span className="font-display text-[19px] font-extrabold tracking-tight">
            NetScan<span className="text-primary">.</span>
          </span>
          <span className="font-mono text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
            // Homelab Monitor
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {(scanning || progress.stage.startsWith('error')) && (
          <div className="flex w-72 flex-col gap-1">
            <div className="flex items-center justify-between font-mono text-xs text-muted-foreground">
              <span className="flex min-w-0 items-center gap-1.5">
                {progress.stage.startsWith('error') ? (
                  <Badge variant="destructive" className="min-w-0 truncate rounded-none font-mono text-xs">
                    {progress.stage}
                  </Badge>
                ) : (
                  <>
                    <Activity className="h-3 w-3 shrink-0 animate-pulse text-[color:var(--accent-cyan)]" />
                    <span className="truncate uppercase tracking-wide">{label}</span>
                    {progress.total > 0 && (
                      <span className="shrink-0 tabular-nums text-[10px]">
                        {progress.done}/{progress.total}
                      </span>
                    )}
                  </>
                )}
              </span>
              {!progress.stage.startsWith('error') && (
                <span className="flex shrink-0 items-center gap-1.5 tabular-nums">
                  {degraded && (
                    <span
                      title="Sin WebSocket — actualizando por sondeo HTTP (más lento)"
                      className="rounded-none border border-warn/50 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-warn"
                    >
                      fallback
                    </span>
                  )}
                  <span className="text-muted-foreground/60">{fmtElapsed(elapsed)}</span>
                  {pct}%
                </span>
              )}
            </div>
            <Progress value={pct} className="h-1 rounded-none" />
          </div>
        )}

        <span className={`flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider ${connected ? 'text-ok' : 'text-destructive'}`}>
          <span
            className={`h-[7px] w-[7px] bg-current ${connected ? 'animate-pulse' : ''}`}
            style={{ boxShadow: '0 0 8px currentColor' }}
          />
          {connected ? <span className="caret">Live</span> : 'Offline'}
        </span>

        <button
          onClick={requestTokenDialog}
          title="Token de API"
          className="press flex h-9 w-9 shrink-0 items-center justify-center rounded-none border border-border text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary"
        >
          <KeyRound className="h-4 w-4" />
        </button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              disabled={scanning}
              className="flex items-center gap-2 rounded-none bg-primary px-4 py-2.5 font-mono text-[12.5px] font-bold uppercase tracking-wider text-primary-foreground shadow-hard-cyan transition-[filter,transform,box-shadow] duration-150 hover:-translate-x-[1px] hover:-translate-y-[1px] hover:brightness-110 hover:shadow-[6px_6px_0_0_rgba(45,226,230,0.28)] active:translate-x-0 active:translate-y-0 disabled:opacity-50 disabled:hover:brightness-100"
            >
              <Play className="h-3.5 w-3.5" />
              {scanning ? 'Scanning…' : 'Ejecutar scan'}
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="w-96 rounded-none border-border bg-popover text-foreground shadow-hard-lg"
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
