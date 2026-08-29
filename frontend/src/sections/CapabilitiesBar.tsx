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
                  className={`flex items-center gap-2 rounded-[10px] border px-3.5 py-2.5 text-[13px] font-semibold ${
                    tool.available
                      ? 'border-[color:var(--teal)]/40 bg-white/[0.09] shadow-[0_0_0_1px_rgba(45,212,191,0.08)_inset]'
                      : 'border-white/10 bg-white/[0.09] opacity-40'
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${tool.available ? 'bg-[color:var(--teal)]' : 'bg-muted-foreground'}`}
                    style={tool.available ? { boxShadow: '0 0 6px var(--teal)' } : undefined}
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
