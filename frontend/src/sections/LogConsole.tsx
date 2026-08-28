import { useEffect, useRef } from 'react'
import { Terminal } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
  return (m && LEVEL_CLASS[m[1]]) || 'text-muted-foreground'
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
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
        <div>
          <CardTitle className="flex items-center gap-2 font-mono text-sm uppercase tracking-wider">
            <Terminal className="h-4 w-4 text-muted-foreground" strokeWidth={1.6} />
            consola
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            Lo que hace el backend ahora mismo — las mismas líneas que en{' '}
            <code>data/netscan.log</code>.
          </p>
        </div>
        <span className="flex shrink-0 items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-ok" />
          {lines.length} líneas
        </span>
      </CardHeader>
      <CardContent>
        <PanelError error={error} />
        <div
          ref={scrollRef}
          onScroll={(e) => {
            const el = e.currentTarget
            wasAtBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
          }}
          className="max-h-64 overflow-y-auto rounded-md bg-background p-3 font-mono text-[11px] leading-relaxed"
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
      </CardContent>
    </Card>
  )
}
