import { Terminal } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'

export default function CapabilitiesBar() {
  const { data } = usePoll(api.capabilities, 60000)
  const tools = data?.tools ?? {}

  return (
    <Card className="bg-card/60">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 font-mono text-sm uppercase tracking-wider">
          <Terminal className="h-4 w-4 text-cyan-400" /> toolchain detectada
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {Object.entries(tools).map(([key, tool]) => (
          <TooltipProvider key={key}>
            <Tooltip>
              <TooltipTrigger>
                <Badge
                  variant={tool.available ? 'secondary' : 'outline'}
                  className={`font-mono text-[10px] ${
                    tool.available ? 'text-emerald-300' : 'text-muted-foreground opacity-50'
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
