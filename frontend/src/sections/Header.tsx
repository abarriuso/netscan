import { useEffect, useRef } from 'react'
import { Activity, ChevronDown, CircleHelp, KeyRound, Play } from 'lucide-react'
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
import Logo from '@/components/Logo'
import { toast } from 'sonner'
import { usePoll, useScanProgress } from '@/hooks/useNetscan'
import { useLastBackLine, useStreamState } from '@/hooks/useFeed'
import { api, requestTokenDialog } from '@/lib/api'
import { fmtDuration } from '@/lib/format'
import { logFront } from '@/lib/telemetry'
import { startTour } from '@/lib/tour'
import type { ScanStage } from '@/types'
import { useI18n, type TextKey } from '@/i18n/context'

const STAGE_KEYS: Record<string, TextKey> = {
  idle: 'stage_idle',
  starting: 'stage_starting',
  arp: 'stage_arp',
  sweep: 'stage_sweep',
  mdns: 'stage_mdns',
  nmap: 'stage_nmap',
  rustscan: 'stage_rustscan',
  nuclei: 'stage_nuclei',
  whatweb: 'stage_whatweb',
  testssl: 'stage_testssl',
  enrich: 'stage_enrich',
  done: 'stage_done',
}

// Backend sources whose latest line is shown under the progress bar.
const SCAN_SOURCES = ['scan', 'discovery', 'mdns', 'ports', 'nmap', 'tool', 'http', 'tls', 'speed', 'vuln', 'dns']

interface ToolAction {
  stage?: ScanStage
  full?: boolean
  /** Tool names (nmap, nuclei…) are not translated; the rest use nameKey. */
  name?: string
  nameKey?: TextKey
  descKey: TextKey
  /** Key into capabilities.tools (or "mdns") that gates availability. */
  requires?: string
  shortcut?: string
}

const SCANS: ToolAction[] = [
  { full: false, nameKey: 'scanQuickName', descKey: 'scanQuickDesc', shortcut: 'R' },
  { full: true, nameKey: 'scanFullName', descKey: 'scanFullDesc', shortcut: 'F' },
]

const TOOLS: ToolAction[] = [
  { stage: 'arp', nameKey: 'toolArpName', descKey: 'toolArpDesc' },
  { stage: 'mdns', name: 'mDNS / Bonjour', descKey: 'toolMdnsDesc', requires: 'mdns' },
  { stage: 'nmap', name: 'nmap', descKey: 'toolNmapDesc', requires: 'nmap' },
  { stage: 'rustscan', name: 'rustscan', descKey: 'toolRustscanDesc', requires: 'rustscan' },
  { stage: 'nuclei', name: 'nuclei', descKey: 'toolNucleiDesc', requires: 'nuclei' },
  { stage: 'whatweb', name: 'whatweb', descKey: 'toolWhatwebDesc', requires: 'whatweb' },
  { stage: 'testssl', name: 'testssl.sh', descKey: 'toolTestsslDesc', requires: 'testssl' },
]

const fmtElapsed = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export default function Header({ onScanDone, onNavigate }: { onScanDone: () => void; onNavigate?: (tab: string) => void }) {
  const { t, lang, setLang } = useI18n()
  const { progress, scanning, elapsed, wsConnected, startScan } = useScanProgress()
  const { data: caps, error: capsError } = usePoll(api.capabilities, 60000)
  const stream = useStreamState()
  const lastScanLine = useLastBackLine(SCAN_SOURCES)
  const apiUp = !capsError
  const isError = progress.stage.startsWith('error')
  const errorText = progress.error ?? progress.stage.replace(/^error:\s*/, '')
  const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0
  // A scan is running but the live socket is down: we're on the HTTP fallback
  // poll (slower updates). Tell the user instead of looking frozen/healthy.
  const degraded = scanning && !wsConnected && !isError
  // Linear ETA for the per-host stage (the long one), only once it has data.
  const eta =
    scanning && progress.stage === 'enrich' && progress.done > 0 && progress.total > progress.done && progress.elapsed_s
      ? (progress.elapsed_s / progress.done) * (progress.total - progress.done)
      : null

  // Toast once per stage change — not again when only the language changes.
  const toastedStage = useRef<string | null>(null)
  useEffect(() => {
    if (progress.stage === toastedStage.current) return
    toastedStage.current = progress.stage
    if (progress.stage === 'done') {
      onScanDone()
      toast.success(t('scanDone'), { description: t('scanDoneDesc', fmtElapsed(elapsed)) })
    } else if (progress.stage.startsWith('error')) {
      toast.error(t('scanError'), { description: errorText, duration: 12000 })
    }
  }, [progress.stage, onScanDone, t, elapsed, errorText])

  const label = isError ? errorText : STAGE_KEYS[progress.stage] ? t(STAGE_KEYS[progress.stage]) : progress.stage

  const isAvailable = (requires?: string) => {
    if (!requires) return true
    if (requires === 'mdns') return caps?.capabilities.mdns ?? true
    return caps?.tools[requires]?.available ?? true
  }

  const run = (action: ToolAction) => {
    logFront('ui', `scan requested: ${action.stage ? `only ${action.stage}` : action.full ? 'full' : 'quick'}`)
    startScan({ full: action.full, only: action.stage })
  }
  const nameOf = (action: ToolAction) => (action.nameKey ? t(action.nameKey) : (action.name ?? ''))

  // R = quick scan, F = full scan (the menu advertised them; now they work).
  const runRef = useRef(run)
  useEffect(() => {
    runRef.current = run
  })
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)) return
      if (document.querySelector('[role="dialog"]')) return
      const key = e.key.toLowerCase()
      if (key !== 'r' && key !== 'f') return
      if (scanning) {
        toast(t('scanAlreadyRunning'))
        return
      }
      e.preventDefault()
      runRef.current(SCANS[key === 'r' ? 0 : 1])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [scanning, t])

  const runtime = caps?.runtime
  const connected = apiUp && stream !== 'offline'

  return (
    <header className="glass hud flex flex-wrap items-center justify-between gap-4 px-6 py-3.5">
      <div className="flex items-center gap-3">
        <Logo size={40} animated />
        <div className="flex flex-col leading-tight">
          <span className="font-display text-[19px] font-extrabold tracking-tight">
            NetScan<span className="text-primary">.</span>
          </span>
          <span className="font-mono text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
            // Homelab Monitor
          </span>
        </div>
        {runtime && (
          <span
            data-tour="mode"
            title={runtime.privileged ? t('modeArpTitle') : t('modeSweepTitle')}
            className={`ml-2 hidden border px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider md:inline ${runtime.privileged ? 'border-ok/50 text-ok' : 'border-warn/50 text-warn'}`}
          >
            {runtime.privileged ? t('modeArp') : t('modeSweep')} · ICMP {runtime.icmp_backend}
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4">
        {(scanning || isError) && (
          <div className="flex w-[22rem] max-w-full flex-col gap-1">
            <div className="flex items-center justify-between font-mono text-xs text-muted-foreground">
              <span className="flex min-w-0 items-center gap-1.5">
                {isError ? (
                  <Badge variant="destructive" className="min-w-0 truncate rounded-none font-mono text-xs" title={errorText}>
                    {t('scanFailedShort')}: {errorText}
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
              {!isError && (
                <span className="flex shrink-0 items-center gap-1.5 tabular-nums">
                  {degraded && (
                    <span
                      title={t('fallbackTitle')}
                      className="rounded-none border border-warn/50 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-warn"
                    >
                      fallback
                    </span>
                  )}
                  <span className="text-muted-foreground/60">{fmtElapsed(elapsed)}</span>
                  {eta != null && <span className="text-muted-foreground/60" title="ETA">~{fmtDuration(eta)}</span>}
                  {pct}%
                </span>
              )}
            </div>
            <Progress value={isError ? 100 : pct} className={`h-1 rounded-none ${isError ? '[&>div]:bg-destructive' : ''}`} />
            {scanning && lastScanLine && (
              <button
                onClick={() => onNavigate?.('live')}
                title={lastScanLine.msg}
                className="truncate text-left font-mono text-[10.5px] text-muted-foreground/80 hover:text-foreground"
              >
                <span className="text-primary/70">[{lastScanLine.source}]</span> {lastScanLine.msg}
              </button>
            )}
          </div>
        )}

        <span
          title={apiUp ? t(`stream_${stream}` as const) : t('apiDown')}
          className={`flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-wider ${connected ? (stream === 'live' ? 'text-ok' : 'text-warn') : 'text-destructive'}`}
        >
          <span
            className={`h-[7px] w-[7px] bg-current ${connected ? 'animate-pulse' : ''}`}
            style={{ boxShadow: '0 0 8px currentColor' }}
          />
          {connected ? <span className="caret">{stream === 'live' ? 'Live' : 'Polling'}</span> : 'Offline'}
        </span>

        <button
          onClick={() => setLang(lang === 'en' ? 'es' : 'en')}
          title={t('switchToLabel')}
          aria-label={t('switchToLabel')}
          lang={lang === 'en' ? 'es' : 'en'}
          className="press flex h-9 shrink-0 items-center justify-center rounded-none border border-border px-2.5 font-mono text-xs font-semibold text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary"
        >
          {t('switchTo')}
        </button>

        <button
          onClick={startTour}
          title={t('tourReplay')}
          aria-label={t('tourReplay')}
          className="press flex h-9 w-9 shrink-0 items-center justify-center rounded-none border border-border text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary"
        >
          <CircleHelp className="h-4 w-4" />
        </button>

        <button
          onClick={requestTokenDialog}
          title={t('apiToken')}
          aria-label={t('apiToken')}
          className="press flex h-9 w-9 shrink-0 items-center justify-center rounded-none border border-border text-muted-foreground transition-colors hover:border-primary/60 hover:text-primary"
        >
          <KeyRound className="h-4 w-4" />
        </button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              data-tour="scan"
              disabled={scanning}
              className="flex items-center gap-2 rounded-none bg-primary px-4 py-2.5 font-mono text-[12.5px] font-bold uppercase tracking-wider text-primary-foreground shadow-hard-cyan transition-[filter,transform,box-shadow] duration-150 hover:-translate-x-[1px] hover:-translate-y-[1px] hover:brightness-110 hover:shadow-[6px_6px_0_0_rgba(45,226,230,0.28)] active:translate-x-0 active:translate-y-0 disabled:opacity-50 disabled:hover:brightness-100"
            >
              <Play className="h-3.5 w-3.5" />
              {scanning ? t('scanning') : t('runScan')}
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="w-96 rounded-none border-border bg-popover text-foreground shadow-hard-lg"
          >
            <DropdownMenuLabel className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {t('menuScans')}
            </DropdownMenuLabel>
            {SCANS.map((action) => (
              <DropdownMenuItem
                key={action.nameKey ?? action.name}
                onSelect={() => run(action)}
                className="items-start gap-3 py-2.5"
              >
                <Play className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-sm font-medium lowercase">{nameOf(action)}</div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{t(action.descKey)}</p>
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
              {t('menuTools')}
            </DropdownMenuLabel>
            {TOOLS.map((action) => {
              const available = isAvailable(action.requires)
              return (
                <DropdownMenuItem
                  key={action.stage}
                  disabled={!available}
                  onSelect={() => run(action)}
                  className="items-start gap-3 py-2.5"
                >
                  <Play className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="font-mono text-sm font-medium lowercase">{nameOf(action)}</div>
                    <p className="mt-0.5 text-xs text-muted-foreground">{t(action.descKey)}</p>
                  </div>
                  {!available && (
                    <span className="shrink-0 rounded border border-border px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
                      {t('notInstalled')}
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
