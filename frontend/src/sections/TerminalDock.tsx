import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, Download, Pause, Play, Search, SquareTerminal, Trash2 } from 'lucide-react'
import { useMergedFeed, useEventStreamConnection, useStreamState } from '@/hooks/useFeed'
import { clearBack } from '@/lib/eventStream'
import { clearFront, logFront } from '@/lib/telemetry'
import { fmtClockMs } from '@/lib/format'
import type { FeedLevel, FeedLine } from '@/types'
import { useI18n, type TextKey } from '@/i18n/context'

// Source → filter group. Backend sources are the `source` field of
// netscan.events; frontend lines are grouped under "front" whatever their source.
const GROUPS: { key: string; label: TextKey; sources: string[] }[] = [
  { key: 'scan', label: 'termGroupScan', sources: ['scan', 'discovery', 'mdns', 'scheduler'] },
  { key: 'ports', label: 'termGroupPorts', sources: ['ports', 'nmap', 'tool'] },
  { key: 'web', label: 'termGroupWeb', sources: ['http', 'tls', 'vuln'] },
  { key: 'net', label: 'termGroupNet', sources: ['dns', 'icmp', 'speed'] },
  { key: 'live', label: 'termGroupLive', sources: ['live'] },
  { key: 'api', label: 'termGroupApi', sources: ['api'] },
  { key: 'alerts', label: 'termGroupAlerts', sources: ['alert', 'security'] },
  { key: 'tools', label: 'termGroupTools', sources: ['toolbox'] },
  { key: 'logs', label: 'termGroupLogs', sources: ['log', 'system', 'integration', 'stream'] },
]

const SOURCE_COLOR: Record<string, string> = {
  scan: 'text-[#2de2e6]',
  discovery: 'text-[#4cc9ff]',
  mdns: 'text-[#4cc9ff]',
  scheduler: 'text-[#4cc9ff]',
  ports: 'text-[#36e09e]',
  nmap: 'text-[#36e09e]',
  tool: 'text-[#36e09e]',
  http: 'text-[#c4a7ff]',
  tls: 'text-[#c4a7ff]',
  vuln: 'text-[#ff4a5e]',
  dns: 'text-[#ffbe37]',
  icmp: 'text-[#ffbe37]',
  speed: 'text-[#ffbe37]',
  live: 'text-[#82909c]',
  api: 'text-[#82909c]',
  alert: 'text-[#ff2fb9]',
  security: 'text-[#ff2fb9]',
  toolbox: 'text-[#2de2e6]',
  log: 'text-[#ffbe37]',
  system: 'text-[#e9ecf1]',
  integration: 'text-[#4cc9ff]',
}

const LEVEL_RANK: Record<FeedLevel, number> = { debug: 0, info: 1, warning: 2, error: 3 }
const LEVEL_GLYPH: Record<FeedLevel, string> = { debug: '·', info: '›', warning: '!', error: '✖' }
const LEVEL_TEXT: Record<FeedLevel, string> = {
  debug: 'text-muted-foreground/70',
  info: 'text-foreground/90',
  warning: 'text-warn',
  error: 'text-destructive',
}
const MAX_RENDER = 800
const HEIGHT_KEY = 'netscan_term_h'
const OPEN_KEY = 'netscan_term_open'

function loadNumber(key: string, fallback: number): number {
  try {
    const v = Number(localStorage.getItem(key))
    return Number.isFinite(v) && v > 0 ? v : fallback
  } catch {
    return fallback
  }
}

function groupOf(line: FeedLine): string {
  if (line.origin === 'front') return 'front'
  return GROUPS.find((g) => g.sources.includes(line.source))?.key ?? 'logs'
}

function matcher(query: string): ((s: string) => boolean) | null {
  const q = query.trim()
  if (!q) return null
  const re = /^\/(.+)\/([a-z]*)$/.exec(q)
  if (re) {
    try {
      const rx = new RegExp(re[1], re[2].includes('i') ? re[2] : `${re[2]}i`)
      return (s) => rx.test(s)
    } catch {
      return null
    }
  }
  const lower = q.toLowerCase()
  return (s) => s.toLowerCase().includes(lower)
}

function Line({ line, open, onToggle }: { line: FeedLine; open: boolean; onToggle: () => void }) {
  const hasData = !!line.data && Object.keys(line.data).length > 0
  return (
    <div className={`group border-l-2 px-2 ${line.level === 'error' ? 'border-l-destructive/70 bg-destructive/[0.06]' : line.level === 'warning' ? 'border-l-warn/60' : 'border-l-transparent'} hover:bg-white/[0.03]`}>
      <button
        type="button"
        onClick={hasData ? onToggle : undefined}
        className={`flex w-full items-start gap-2 py-[1px] text-left ${hasData ? 'cursor-pointer' : 'cursor-default'}`}
      >
        <span className="shrink-0 tabular-nums text-muted-foreground/60">{fmtClockMs(line.t)}</span>
        <span
          className={`w-[22px] shrink-0 text-center text-[10px] font-bold ${line.origin === 'back' ? 'text-primary/80' : 'text-[color:var(--accent-magenta)]/80'}`}
          title={line.origin === 'back' ? 'backend' : 'frontend'}
        >
          {line.origin === 'back' ? 'BE' : 'FE'}
        </span>
        <span className={`w-[78px] shrink-0 truncate ${SOURCE_COLOR[line.source] ?? 'text-muted-foreground'}`}>{line.source}</span>
        <span className={`w-3 shrink-0 text-center ${LEVEL_TEXT[line.level]}`}>{LEVEL_GLYPH[line.level]}</span>
        <span className={`min-w-0 flex-1 whitespace-pre-wrap break-words ${LEVEL_TEXT[line.level]}`}>{line.msg}</span>
        {hasData && <span className="shrink-0 text-[10px] text-muted-foreground/50 opacity-0 group-hover:opacity-100">{open ? '−' : '+'}{'{}'}</span>}
      </button>
      {open && hasData && (
        <pre className="mb-1 ml-[150px] overflow-x-auto rounded-none border border-border/60 bg-black/40 p-2 text-[11px] text-muted-foreground">
          {JSON.stringify(line.data, null, 2)}
        </pre>
      )}
    </div>
  )
}

/** Bottom-docked terminal: the live stream of everything NetScan does —
 *  backend events (scan stages, every port/HTTP/TLS/DNS probe, external
 *  commands, live-monitor ticks, API calls as the server sees them) merged
 *  with the browser's own activity (every request with status and timing,
 *  WebSocket state, errors). Toggle with the backquote key. */
export default function TerminalDock() {
  const { t } = useI18n()
  useEventStreamConnection()
  const feed = useMergedFeed()
  const stream = useStreamState()
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(OPEN_KEY) === '1'
    } catch {
      return false
    }
  })
  const [height, setHeight] = useState(() => loadNumber(HEIGHT_KEY, 320))
  const [groups, setGroups] = useState<Set<string>>(new Set())
  const [minLevel, setMinLevel] = useState<FeedLevel>('debug')
  const [query, setQuery] = useState('')
  const [paused, setPaused] = useState<FeedLine[] | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const scrollRef = useRef<HTMLDivElement>(null)
  const follow = useRef(true)

  const toggleOpen = useCallback(() => {
    setOpen((o) => {
      try {
        localStorage.setItem(OPEN_KEY, o ? '0' : '1')
      } catch {
        /* storage disabled */
      }
      return !o
    })
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return
      if (e.key === '`' || e.key === 'º') {
        e.preventDefault()
        toggleOpen()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toggleOpen])

  const source = paused ?? feed
  const match = useMemo(() => matcher(query), [query])
  const visible = useMemo(() => {
    const min = LEVEL_RANK[minLevel]
    const out = source.filter(
      (l) =>
        LEVEL_RANK[l.level] >= min &&
        (groups.size === 0 || groups.has(groupOf(l))) &&
        (!match || match(`${l.source} ${l.msg}`)),
    )
    return out.length > MAX_RENDER ? out.slice(out.length - MAX_RENDER) : out
  }, [source, minLevel, groups, match])

  useEffect(() => {
    const el = scrollRef.current
    if (el && follow.current && open) el.scrollTop = el.scrollHeight
  }, [visible, open])

  // Wall clock for the events/min rate, refreshed off-render.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 5000)
    return () => clearInterval(id)
  }, [])
  const perMin = useMemo(() => feed.filter((l) => now - l.t < 60_000).length, [feed, now])
  const counts = useMemo(() => {
    let warn = 0
    let err = 0
    let be = 0
    for (const l of feed) {
      if (l.origin === 'back') be++
      if (l.level === 'warning') warn++
      else if (l.level === 'error') err++
    }
    return { warn, err, be, fe: feed.length - be }
  }, [feed])
  const last = useMemo(() => {
    for (let i = feed.length - 1; i >= 0; i--) if (feed[i].level !== 'debug') return feed[i]
    return feed[feed.length - 1]
  }, [feed])
  const newWhilePaused = paused ? feed.length - paused.length : 0

  const startResize = (e: React.MouseEvent) => {
    e.preventDefault()
    const startY = e.clientY
    const startH = height
    const onMove = (ev: MouseEvent) => {
      const h = Math.min(Math.max(160, startH + (startY - ev.clientY)), Math.round(window.innerHeight * 0.85))
      setHeight(h)
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      setHeight((h) => {
        try {
          localStorage.setItem(HEIGHT_KEY, String(h))
        } catch {
          /* storage disabled */
        }
        return h
      })
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const download = () => {
    const text = visible
      .map(
        (l) =>
          `${new Date(l.t).toISOString()}\t${l.origin === 'back' ? 'BE' : 'FE'}\t${l.source}\t${l.level}\t${l.msg}` +
          (l.data ? `\t${JSON.stringify(l.data)}` : ''),
      )
      .join('\n')
    const blob = new Blob([text + '\n'], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `netscan-terminal-${new Date().toISOString().replace(/[:.]/g, '-')}.log`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    logFront('ui', `terminal exported: ${visible.length} lines`)
  }

  const streamPill =
    stream === 'live'
      ? { cls: 'border-ok/50 text-ok', dot: 'bg-ok', label: t('termLive') }
      : stream === 'polling'
        ? { cls: 'border-warn/50 text-warn', dot: 'bg-warn', label: t('termPolling') }
        : stream === 'offline'
          ? { cls: 'border-destructive/60 text-destructive', dot: 'bg-destructive', label: t('termOffline') }
          : { cls: 'border-border text-muted-foreground', dot: 'bg-muted-foreground', label: t('termConnecting') }

  const toggleGroup = (key: string) =>
    setGroups((g) => {
      const next = new Set(g)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const chip = (active: boolean) =>
    `rounded-none border px-2 py-0.5 text-[10.5px] uppercase tracking-wider transition-colors ${active ? 'border-primary/60 bg-primary/[0.12] text-primary' : 'border-border text-muted-foreground hover:text-foreground'}`

  return (
    <>
      <div aria-hidden style={{ height: open ? height + 8 : 46 }} />
      <section
        data-tour="terminal"
        aria-label={t('termTitle')}
        className="fixed inset-x-0 bottom-0 z-40 border-t border-primary/30 bg-[rgb(6_8_11/0.97)] font-mono text-[12px] shadow-[0_-8px_24px_rgba(0,0,0,0.45)] backdrop-blur"
      >
        {open && (
          <div
            onMouseDown={startResize}
            className="absolute inset-x-0 -top-1 h-2 cursor-ns-resize"
            title="resize"
            aria-hidden
          />
        )}
        {/* status bar — always visible */}
        <div className="flex h-[38px] items-center gap-3 px-3 sm:px-4">
          <button onClick={toggleOpen} className="press flex shrink-0 items-center gap-2 text-primary" aria-expanded={open}>
            <SquareTerminal className="h-4 w-4" />
            <span className="hidden text-[11px] font-bold uppercase tracking-[0.16em] sm:inline">{t('termTitle')}</span>
            {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
          </button>
          <span className={`flex shrink-0 items-center gap-1.5 border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${streamPill.cls}`}>
            <span className={`h-1.5 w-1.5 ${streamPill.dot} ${stream === 'live' ? 'animate-pulse' : ''}`} />
            {streamPill.label}
          </span>
          <span className="hidden shrink-0 tabular-nums text-[10.5px] text-muted-foreground md:inline">
            BE {counts.be.toLocaleString()} · FE {counts.fe.toLocaleString()} · {t('termRate', perMin)}
          </span>
          <button
            onClick={toggleOpen}
            className={`min-w-0 flex-1 truncate text-left text-[11.5px] ${last ? LEVEL_TEXT[last.level] : 'text-muted-foreground'}`}
            title={last?.msg}
          >
            {last ? (
              <>
                <span className={`mr-2 ${SOURCE_COLOR[last.source] ?? 'text-muted-foreground'}`}>[{last.source}]</span>
                {last.msg}
              </>
            ) : (
              t('termEmpty')
            )}
          </button>
          {counts.warn > 0 && (
            <span className="shrink-0 border border-warn/50 px-1.5 text-[10px] font-bold tabular-nums text-warn" title="warnings">
              ! {counts.warn}
            </span>
          )}
          {counts.err > 0 && (
            <span className="shrink-0 border border-destructive/60 px-1.5 text-[10px] font-bold tabular-nums text-destructive" title="errors">
              ✖ {counts.err}
            </span>
          )}
          <kbd className="hidden shrink-0 border border-border px-1.5 text-[10px] text-muted-foreground lg:inline" title={t('termHotkey')}>
            `
          </kbd>
        </div>

        {open && (
          <div style={{ height: height - 38 }} className="flex flex-col border-t border-border/70">
            {/* toolbar */}
            <div className="flex flex-wrap items-center gap-1.5 border-b border-border/70 px-3 py-1.5 sm:px-4">
              <button className={chip(groups.size === 0)} onClick={() => setGroups(new Set())}>
                {t('termGroupAll')}
              </button>
              {GROUPS.map((g) => (
                <button key={g.key} className={chip(groups.has(g.key))} onClick={() => toggleGroup(g.key)}>
                  {t(g.label)}
                </button>
              ))}
              <button className={chip(groups.has('front'))} onClick={() => toggleGroup('front')}>
                {t('termGroupFront')}
              </button>
              <span className="mx-1 h-4 w-px bg-border" />
              {(['debug', 'info', 'warning', 'error'] as FeedLevel[]).map((lvl) => (
                <button key={lvl} className={chip(minLevel === lvl)} onClick={() => setMinLevel(lvl)} title={t('termLevel')}>
                  ≥{lvl}
                </button>
              ))}
              <div className="ml-auto flex items-center gap-1.5">
                <label className="flex items-center gap-1 border border-border px-1.5">
                  <Search className="h-3 w-3 text-muted-foreground" />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={t('termSearch')}
                    aria-label={t('termSearch')}
                    className="h-6 w-36 bg-transparent text-[11px] outline-none placeholder:text-muted-foreground/60 sm:w-56"
                  />
                </label>
                <button
                  className={chip(!!paused)}
                  onClick={() => setPaused((p) => (p ? null : feed))}
                  title={paused ? t('termResume') : t('termPause')}
                >
                  {paused ? <Play className="inline h-3 w-3" /> : <Pause className="inline h-3 w-3" />}
                  {paused && newWhilePaused > 0 ? ` ${t('termNew', newWhilePaused)}` : ''}
                </button>
                <button
                  className={chip(false)}
                  onClick={() => {
                    clearBack()
                    clearFront()
                    setPaused(null)
                  }}
                  title={t('termClear')}
                >
                  <Trash2 className="inline h-3 w-3" />
                </button>
                <button className={chip(false)} onClick={download} title={t('termDownload')}>
                  <Download className="inline h-3 w-3" />
                </button>
              </div>
            </div>
            {/* lines */}
            <div
              ref={scrollRef}
              onScroll={(e) => {
                const el = e.currentTarget
                follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32
              }}
              className="min-h-0 flex-1 overflow-y-auto py-1 leading-[1.6]"
              role="log"
              aria-live="off"
            >
              {visible.length === 0 ? (
                <p className="px-4 py-3 text-muted-foreground">{t('termEmpty')}</p>
              ) : (
                visible.map((line) => (
                  <Line
                    key={line.id}
                    line={line}
                    open={expanded.has(line.id)}
                    onToggle={() =>
                      setExpanded((s) => {
                        const next = new Set(s)
                        if (next.has(line.id)) next.delete(line.id)
                        else next.add(line.id)
                        return next
                      })
                    }
                  />
                ))
              )}
            </div>
          </div>
        )}
      </section>
    </>
  )
}
