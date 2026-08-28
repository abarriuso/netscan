import { Globe, ShieldAlert, ShieldCheck } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { usePoll } from '@/hooks/useNetscan'
import { fetchLatestScan } from '@/lib/api'
import PanelError from './PanelError'

function CertBadge({ days, selfSigned }: { days: number | null; selfSigned: boolean }) {
  if (days == null) return null
  const cls = days < 0 ? 'text-destructive' : days < 30 ? 'text-warn' : 'text-ok'
  return (
    <span className={`font-mono text-[10px] ${cls}`}>
      {days < 0 ? `caducado hace ${-days}d` : `${days}d`}
      {selfSigned ? ' · autofirmado' : ''}
    </span>
  )
}

export default function ServicesPanel({ refreshKey }: { refreshKey: number }) {
  const { data: scan, error } = usePoll(fetchLatestScan, 20000, refreshKey)

  const webServices = (scan?.devices ?? []).flatMap((d) =>
    d.http.map((h) => ({ ip: d.ip, name: d.hostname || d.mdns_name || d.ip, ...h })),
  )
  const vulns = scan?.vulnerabilities ?? []

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 font-mono text-sm uppercase tracking-wider">
          <Globe className="h-4 w-4 text-muted-foreground" strokeWidth={1.6} /> servicios web &amp; tls
          {scan && (
            <span className="ml-auto font-mono text-[10px] font-normal text-muted-foreground">
              último scan: {new Date(scan.started_at).toLocaleTimeString()} · {scan.duration_s}s
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs">
        <PanelError error={error} />
        {!scan && !error && <p className="text-muted-foreground">sin scans todavía</p>}
        {scan && webServices.length === 0 && (
          <p className="text-muted-foreground">ninguna web UI detectada en el último scan</p>
        )}
        <div className="grid gap-1.5 md:grid-cols-2">
          {webServices.map((svc) => (
            <div
              key={svc.url}
              className="flex items-center gap-3 rounded border border-border/60 px-3 py-2"
            >
              {svc.tls && (svc.tls.days_remaining ?? 99) < 30 ? (
                <ShieldAlert className="h-4 w-4 shrink-0 text-warn" strokeWidth={1.6} />
              ) : (
                <ShieldCheck className="h-4 w-4 shrink-0 text-ok" strokeWidth={1.6} />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <a
                    href={svc.url}
                    target="_blank"
                    rel="noreferrer"
                    className="truncate font-mono font-semibold text-primary hover:underline"
                  >
                    {svc.url.replace(/^https?:\/\//, '')}
                  </a>
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {svc.status_code}
                  </Badge>
                </div>
                <p className="truncate text-muted-foreground">
                  {svc.title || svc.server || svc.name}
                  {svc.title && svc.server ? ` · ${svc.server}` : ''}
                </p>
              </div>
              {svc.tls && (
                <div className="text-right">
                  <CertBadge days={svc.tls.days_remaining} selfSigned={svc.tls.self_signed} />
                  <p className="font-mono text-[10px] text-muted-foreground">{svc.tls.version}</p>
                </div>
              )}
            </div>
          ))}
        </div>
        {vulns.length > 0 && (
          <div className="mt-3 space-y-1">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-destructive">
              hallazgos nuclei ({vulns.length})
            </p>
            {vulns.map((v, i) => (
              <div key={i} className="flex items-center gap-2 rounded bg-destructive/10 px-3 py-1.5">
                <Badge variant="destructive" className="font-mono text-[10px]">{v.severity}</Badge>
                <span className="truncate">{v.name || v.template}</span>
                <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                  {v.matched_at.replace(/^https?:\/\//, '')}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
