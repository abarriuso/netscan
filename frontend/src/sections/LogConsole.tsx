import { useEffect, useRef } from 'react'
import { GlassPanel } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import PanelError from './PanelError'

const LEVEL_CLASS: Record<string, string> = {
  ERROR: 'text-destructive',
  CRITICAL: 'text-destructive',
  WARNING: 'text-warn',
}

/** Color a log line by the level netscan's logging.Formatter prints, e.g.
 *  "2026-08-28 17:07:33,587 INFO netscan: ...". */
function levelClass(line: string): string {
  const m = line.match(/\s(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s/)
  return (m && LEVEL_CLASS[m[1]]) || 'text-[color:var(--teal)]'
}

/** Live tail of netscan.log — what the backend is doing right now, without
 *  needing a separate terminal window open. */
export default function LogConsole() {
  const { data, error } = usePoll(() => api.logs(300), 2500)
  const lines = data?.lines ?? []
  const scrollRef = useRef<HTMLDivElement>(null)
  const wasAtBottom = useRef(true)

  useEffect(() => {
    const el = scrollRef.current
    if (el && wasAtBottom.current) el.scrollTop = el.scrollHeight
  }, [lines.length])

  return (
    <GlassPanel title="Consola en vivo" meta="tail -f netscan.log">
      <PanelError error={error} />
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget
          wasAtBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
        }}
        className="max-h-[210px] overflow-y-auto rounded-[10px] border border-white/[0.07] bg-black/35 p-3.5 font-mono text-[12px] leading-[1.85]"
      >
        {lines.length === 0 ? (
          <p className="text-muted-foreground">sin actividad todavía</p>
        ) : (
          lines.map((line, i) => (
            <div key={i} className={`whitespace-pre-wrap ${levelClass(line)}`}>
              {line}
            </div>
          ))
        )}
      </div>
    </GlassPanel>
  )
}
