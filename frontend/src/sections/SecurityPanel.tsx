import { useState } from 'react'
import { ChevronDown, ChevronRight, ShieldAlert, ShieldCheck } from 'lucide-react'
import { GlassPanel } from '@/components/metrics'
import { RoleIcon } from '@/components/RoleIcon'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import { openDeviceDetail } from '@/lib/deviceDetail'
import { LEVEL_STYLE } from '@/lib/risk'
import type { RiskLevel, SecurityDevice } from '@/types'
import PanelError from './PanelError'
import { useI18n } from '@/i18n/context'

export function RiskBadge({ score, level }: { score: number; level: RiskLevel }) {
  const { t } = useI18n()
  return (
    <span className={`inline-flex items-center gap-1 border px-1.5 py-0.5 font-mono text-[10.5px] font-bold uppercase tracking-wide ${LEVEL_STYLE[level].badge}`}>
      {score} · {t('riskLevel', level)}
    </span>
  )
}

export function FactorList({ device }: { device: Pick<SecurityDevice, 'factors'> }) {
  const { t } = useI18n()
  if (!device.factors.length) return <p className="font-mono text-xs text-ok">{t('secNoFactors')}</p>
  return (
    <ul className="space-y-1.5">
      {device.factors.map((f) => (
        <li key={f.id} className="grid grid-cols-[46px_1fr] gap-2 border-l-2 border-border/70 pl-2 text-xs">
          <span className={`font-mono font-bold tabular-nums ${LEVEL_STYLE[f.severity].text}`}>+{f.points}</span>
          <span>
            <span className="font-semibold">{t('riskTitle', f.id, f.title)}</span>
            {f.evidence && <span className="block font-mono text-[11px] text-muted-foreground">{f.evidence}</span>}
            {f.remediation && <span className="block text-[11px] text-primary/80">→ {t('riskFix', f.id, f.remediation)}</span>}
          </span>
        </li>
      ))}
    </ul>
  )
}

function DeviceRow({ d }: { d: SecurityDevice }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-border/60 bg-white/[0.02]">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-white/[0.03]">
        {open ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
        <RoleIcon role={d.role} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-semibold">{d.name}</span>
          <span className="block font-mono text-[10.5px] text-muted-foreground">
            {d.ip} · {d.vendor || '—'} · {t('role', d.role)}
            {!d.trusted && <span className="ml-1 text-destructive">· {t('secUntrusted')}</span>}
          </span>
        </span>
        <span className="hidden w-40 sm:block">
          <span className="block h-1.5 w-full bg-white/[0.07]">
            <span className={`block h-full ${LEVEL_STYLE[d.level].bar}`} style={{ width: `${d.score}%` }} />
          </span>
        </span>
        <RiskBadge score={d.score} level={d.level} />
      </button>
      {open && (
        <div className="space-y-2 border-t border-border/60 px-3 py-3">
          <FactorList device={d} />
          <button onClick={() => openDeviceDetail(d.mac)} className="font-mono text-[11px] text-primary hover:underline">
            {t('secOpenDevice')} →
          </button>
        </div>
      )}
    </div>
  )
}

/** Security posture: per-device risk with itemized, explained factors;
 *  exposed services, certificates, scanner findings, gateway integrity. */
export default function SecurityPanel() {
  const { t, locale } = useI18n()
  const { data, error, refresh } = usePoll(api.security, 30000)
  const s = data?.summary

  return (
    <div className="space-y-[18px]">
      <PanelError error={error} onRetry={refresh} />
      <div className="grid grid-cols-2 gap-[14px] md:grid-cols-4 xl:grid-cols-8">
        <SecStat
          label={t('secNetwork')}
          value={s?.network_level ? t('riskLevel', s.network_level) : '—'}
          cls={s?.network_level ? LEVEL_STYLE[s.network_level].text : ''}
          sub={s?.avg_score != null ? t('secAvgScore', s.avg_score) : undefined}
        />
        {(['critical', 'high', 'medium', 'low'] as RiskLevel[]).map((lvl) => (
          <SecStat key={lvl} label={t('riskLevel', lvl)} value={String(s?.by_level[lvl] ?? 0)} cls={LEVEL_STYLE[lvl].text} />
        ))}
        <SecStat label={t('secUntrustedN')} value={String(s?.untrusted ?? 0)} cls={s?.untrusted ? 'text-warn' : 'text-ok'} />
        <SecStat label={t('secRandomMacs')} value={String(s?.randomized_macs ?? 0)} />
        <SecStat
          label={t('secCertsExpiring')}
          value={String(s?.certs_expiring_30d ?? 0)}
          cls={s?.certs_expiring_30d ? 'text-warn' : 'text-ok'}
          sub={t('secCertsTotal', s?.certificates ?? 0)}
        />
      </div>

      <div className="grid gap-[18px] xl:grid-cols-[1.5fr_1fr]">
        <GlassPanel title={t('secRanking')} meta={t('secScale')}>
          {data && data.devices.length === 0 && <p className="text-sm text-muted-foreground">{t('noData')}</p>}
          <div className="space-y-1.5">
            {(data?.devices ?? []).map((d) => (
              <DeviceRow key={d.mac} d={d} />
            ))}
          </div>
        </GlassPanel>

        <div className="space-y-[18px]">
          <GlassPanel title={t('secGateway')}>
            {data?.gateway.ip ? (
              <div className="space-y-2 font-mono text-xs">
                <p className="flex items-center gap-2">
                  {data.gateway.history.length ? (
                    <ShieldAlert className="h-4 w-4 text-destructive" />
                  ) : (
                    <ShieldCheck className="h-4 w-4 text-ok" />
                  )}
                  {data.gateway.ip} → {data.gateway.mac || '?'}
                </p>
                <p className="text-muted-foreground">{t('secGatewayHint')}</p>
                {data.gateway.history.map((h) => (
                  <p key={h.at} className="border-l-2 border-destructive/70 pl-2 text-destructive">
                    {new Date(h.at).toLocaleString(locale)} — {h.detail}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">{t('liveNoGateway')}</p>
            )}
            {(data?.conflicts ?? []).map((c) => (
              <p key={c.ip} className="mt-2 border-l-2 border-destructive/70 pl-2 font-mono text-xs text-destructive">
                {t('secConflict', c.ip, c.macs.join(', '))}
              </p>
            ))}
          </GlassPanel>

          <GlassPanel title={t('secExposure')} meta={t('secExposureMeta')}>
            {(data?.exposure ?? []).length === 0 ? (
              <p className="font-mono text-xs text-ok">{t('secNoExposure')}</p>
            ) : (
              <ul className="space-y-1 font-mono text-xs">
                {data!.exposure.map((e) => (
                  <li key={e.port} className="flex justify-between border-b border-border/40 py-1">
                    <span>{e.port}/tcp</span>
                    <span className="text-warn">{t('secOnDevices', e.devices)}</span>
                  </li>
                ))}
              </ul>
            )}
          </GlassPanel>
        </div>
      </div>

      <GlassPanel title={t('secCerts')} meta={t('secCertsTotal', data?.certificates.length ?? 0)}>
        {(data?.certificates ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('noWebUI')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] font-mono text-xs">
              <thead className="text-left text-[10.5px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="py-1 font-medium">URL</th>
                  <th className="font-medium">{t('secSubject')}</th>
                  <th className="font-medium">{t('secIssuer')}</th>
                  <th className="font-medium">TLS</th>
                  <th className="text-right font-medium">{t('secExpires')}</th>
                </tr>
              </thead>
              <tbody>
                {data!.certificates.map((c) => {
                  const days = c.days_remaining
                  const cls = days == null ? '' : days < 0 ? 'text-destructive' : days < 30 ? 'text-warn' : 'text-ok'
                  return (
                    <tr key={c.url} className="border-t border-border/40">
                      <td className="py-1.5">
                        <a href={c.url} target="_blank" rel="noreferrer" className="hover:text-primary">
                          {c.url.replace(/^https:\/\//, '')}
                        </a>
                      </td>
                      <td className="max-w-[220px] truncate" title={c.subject}>{c.subject || '—'}</td>
                      <td className="max-w-[220px] truncate text-muted-foreground" title={c.issuer}>
                        {c.issuer || '—'}
                        {c.self_signed && <span className="ml-1 text-warn">({t('secSelfSigned')})</span>}
                      </td>
                      <td className={c.version === 'TLSv1' || c.version === 'TLSv1.1' ? 'text-destructive' : ''}>{c.version}</td>
                      <td className={`text-right font-semibold ${cls}`}>{days == null ? '—' : days < 0 ? t('certExpired', -days) : `${days} d`}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </GlassPanel>

      <GlassPanel title={t('findings', data?.findings.length ?? 0)}>
        {(data?.findings ?? []).length === 0 ? (
          <p className="font-mono text-xs text-muted-foreground">{t('secNoFindings')}</p>
        ) : (
          <div className="space-y-1.5">
            {data!.findings.map((f, i) => (
              <div key={i} className="flex items-center gap-2 border-l-2 border-l-destructive/70 bg-destructive/[0.07] px-3 py-1.5 text-xs">
                <span className={`border px-1.5 font-mono text-[10px] font-bold uppercase ${LEVEL_STYLE[(['low', 'medium', 'high', 'critical'].includes(f.severity) ? f.severity : 'info') as RiskLevel].badge}`}>
                  {f.severity}
                </span>
                {f.tool && <span className="font-mono text-[10.5px] text-muted-foreground">{f.tool}</span>}
                <span className="truncate">{f.name || f.template}</span>
                <span className="ml-auto truncate font-mono text-[11px] text-muted-foreground">{f.matched_at}</span>
              </div>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  )
}

function SecStat({ label, value, cls = '', sub }: { label: string; value: string; cls?: string; sub?: string }) {
  return (
    <div className="glass flex flex-col gap-1 px-4 py-3">
      <span className="kbd-label">{label}</span>
      <span className={`font-display text-[22px] font-extrabold uppercase leading-none ${cls}`}>{value}</span>
      {sub && <span className="font-mono text-[10.5px] text-muted-foreground">{sub}</span>}
    </div>
  )
}
