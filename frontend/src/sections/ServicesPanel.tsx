import { GlassPanel } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { fetchLatestScan } from '@/lib/api'
import PanelError from './PanelError'

function CertBadge({ days, selfSigned, tls }: { days: number | null; selfSigned: boolean; tls: boolean }) {
  if (!tls) return <span className="text-[11.5px] font-semibold text-warn">sin TLS · HTTP plano</span>
  if (days == null) return null
  const cls = days < 0 ? 'text-destructive' : days < 30 ? 'text-warn' : 'text-ok'
  return (
    <span className={`text-[11.5px] font-semibold ${cls}`}>
      {days < 0 ? `caducado hace ${-days}d` : `cert válido · ${days}d restantes`}
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
    <GlassPanel
      title="Servicios web & TLS"
      meta={scan ? `${webServices.length} descubiertos · último scan ${new Date(scan.started_at).toLocaleTimeString()}` : undefined}
    >
      <PanelError error={error} />
      {!scan && !error && <p className="text-sm text-muted-foreground">sin scans todavía</p>}
      {scan && webServices.length === 0 && (
        <p className="text-sm text-muted-foreground">ninguna web UI detectada en el último scan</p>
      )}
      <div className="grid gap-3.5 md:grid-cols-2 xl:grid-cols-3">
        {webServices.map((svc) => (
          <div key={svc.url} className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3.5">
            <a
              href={svc.url}
              target="_blank"
              rel="noreferrer"
              className="truncate font-mono text-[12.5px] font-semibold text-foreground hover:text-primary"
            >
              {svc.url.replace(/^https?:\/\//, '')}
            </a>
            <div className="flex items-center justify-between">
              <CertBadge days={svc.tls?.days_remaining ?? null} selfSigned={!!svc.tls?.self_signed} tls={!!svc.tls} />
              <span className="text-[11px] text-muted-foreground">{svc.status_code}</span>
            </div>
            <p className="truncate text-[11.5px] text-muted-foreground">
              {svc.title || svc.server || svc.name}
              {svc.title && svc.server ? ` · ${svc.server}` : ''}
            </p>
            {(svc.tech ?? []).length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {(svc.tech ?? []).slice(0, 6).map((t) => (
                  <span
                    key={t}
                    className="rounded-[6px] border border-[color:var(--blue)]/30 bg-[color:var(--blue)]/[0.12] px-2 py-0.5 text-[10.5px] text-[#a8c8ff]"
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      {vulns.length > 0 && (
        <div className="mt-4 space-y-1.5 border-t border-white/10 pt-4">
          <p className="text-[10.5px] font-bold uppercase tracking-wider text-destructive">
            hallazgos de seguridad ({vulns.length})
          </p>
          {vulns.map((v, i) => (
            <div key={i} className="flex items-center gap-2 rounded-lg bg-destructive/10 px-3 py-2 text-[12.5px]">
              <span className="rounded-full bg-destructive px-2 py-0.5 text-[10px] font-bold text-white">{v.severity}</span>
              {v.tool && <span className="font-mono text-[10.5px] text-muted-foreground">{v.tool}</span>}
              <span className="truncate">{v.name || v.template}</span>
              <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                {v.matched_at.replace(/^https?:\/\//, '')}
              </span>
            </div>
          ))}
        </div>
      )}
    </GlassPanel>
  )
}
