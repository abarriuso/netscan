import { Terminal } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import PanelError from './PanelError'

export default function CapabilitiesBar() {
  const { data, error } = usePoll(api.capabilities, 60000)
  const tools = data?.tools ?? {}

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 font-mono text-sm uppercase tracking-wider">
          <Terminal className="h-4 w-4 text-muted-foreground" strokeWidth={1.6} /> toolchain detectada
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <PanelError error={error} />
        {Object.entries(tools).map(([key, tool]) => (
          <TooltipProvider key={key}>
            <Tooltip>
              <TooltipTrigger>
                <Badge
                  variant={tool.available ? 'secondary' : 'outline'}
                  className={`font-mono text-[10px] ${
                    tool.available ? 'text-ok' : 'text-muted-foreground opacity-50'
                  }`}
                >
                  {key}
                </Badge>
              </TooltipTrigger>
              <TooltipContent className="max-w-64 font-mono text-xs">
                <p>{tool.purpose}</p>
                <p className="mt-1 text-muted-foreground">licencia: {tool.license}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ))}
        {Object.keys(tools).length === 0 && (
          <p className="text-xs text-muted-foreground">backend no accesible</p>
        )}
      </CardContent>
    </Card>
  )
}
