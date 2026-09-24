import { GlassPanel } from '@/components/metrics'
import { usePoll } from '@/hooks/useNetscan'
import { fetchLatestScan } from '@/lib/api'
import PanelError from './PanelError'
import { useI18n } from '@/i18n/context'

function CertBadge({ days, selfSigned, tls }: { days: number | null; selfSigned: boolean; tls: boolean }) {
  const { t } = useI18n()
  if (!tls) return <span className="text-xs font-semibold text-warn">{t('noTls')}</span>
  if (days == null) return null
  const cls = days < 0 ? 'text-destructive' : days < 30 ? 'text-warn' : 'text-ok'
  return (
    <span className={`text-xs font-semibold ${cls}`}>
      {days < 0 ? t('certExpired', -days) : t('certValid', days)}
      {selfSigned ? t('selfSigned') : ''}
    </span>
  )
}

export default function ServicesPanel({ refreshKey }: { refreshKey: number }) {
  const { t } = useI18n()
  const { data: scan, error } = usePoll(fetchLatestScan, 20000, refreshKey)

  const webServices = (scan?.devices ?? []).flatMap((d) =>
    d.http.map((h) => ({ ip: d.ip, name: d.hostname || d.mdns_name || d.ip, ...h })),
  )
  const vulns = scan?.vulnerabilities ?? []

  return (
    <GlassPanel
      title={t('servicesTitle')}
      meta={scan ? t('servicesMeta', webServices.length, new Date(scan.started_at).toLocaleTimeString()) : undefined}
    >
      <PanelError error={error} />
      {!scan && !error && <p className="text-sm text-muted-foreground">{t('noScans')}</p>}
      {scan && webServices.length === 0 && (
        <p className="text-sm text-muted-foreground">{t('noWebUI')}</p>
      )}
      <div className="grid gap-3.5 md:grid-cols-2 xl:grid-cols-3">
        {webServices.map((svc) => (
          <div key={svc.url} className="flex flex-col gap-2 rounded-none border border-border bg-secondary/50 p-3.5">
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
            <p className="truncate text-xs text-muted-foreground">
              {svc.title || svc.server || svc.name}
              {svc.title && svc.server ? ` · ${svc.server}` : ''}
            </p>
            {(svc.tech ?? []).length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {(svc.tech ?? []).slice(0, 6).map((t) => (
                  <span
                    key={t}
                    className="rounded-none border border-[color:var(--accent-sky)]/40 bg-[color:var(--accent-sky)]/[0.1] px-2 py-0.5 font-mono text-[10.5px] text-[color:var(--accent-sky)]"
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
            {t('findings', vulns.length)}
          </p>
          {vulns.map((v, i) => (
            <div key={i} className="flex items-center gap-2 rounded-none border-l-2 border-l-destructive/70 bg-destructive/10 px-3 py-2 text-[12.5px]">
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
