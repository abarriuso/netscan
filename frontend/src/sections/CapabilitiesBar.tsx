import { GlassPanel } from '@/components/metrics'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import PanelError from './PanelError'

export default function CapabilitiesBar() {
  const { data, error } = usePoll(api.capabilities, 60000)
  const tools = data?.tools ?? {}
  const available = Object.values(tools).filter((t) => t.available).length
  const total = Object.keys(tools).length

  return (
    <GlassPanel title="Toolchain & Capacidades" meta={total ? `${available} de ${total} disponibles` : undefined}>
      <PanelError error={error} />
      <div className="flex flex-wrap gap-2.5">
        {Object.entries(tools).map(([key, tool]) => (
          <TooltipProvider key={key}>
            <Tooltip>
              <TooltipTrigger>
                <span
                  className={`flex items-center gap-2 rounded-none border px-3.5 py-2.5 font-mono text-[12px] font-semibold uppercase tracking-wide ${
                    tool.available
                      ? 'border-primary/40 bg-primary/[0.06] text-foreground shadow-[inset_0_0_0_1px_rgba(45,226,230,0.08)]'
                      : 'border-border bg-secondary/40 opacity-40'
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 ${tool.available ? 'bg-primary' : 'bg-muted-foreground'}`}
                    style={tool.available ? { boxShadow: '0 0 6px var(--accent-cyan)' } : undefined}
                  />
                  {key}
                </span>
              </TooltipTrigger>
              <TooltipContent className="max-w-64 text-xs">
                <p>{tool.purpose}</p>
                <p className="mt-1 text-muted-foreground">licencia: {tool.license}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ))}
        {total === 0 && <p className="text-sm text-muted-foreground">backend no accesible</p>}
      </div>
    </GlassPanel>
  )
}
