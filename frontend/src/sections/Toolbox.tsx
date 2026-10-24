import { useState } from 'react'
import { Loader2, Play } from 'lucide-react'
import { GlassPanel } from '@/components/metrics'
import { api } from '@/lib/api'
import { fmtMs, fmtBytes, fmtMbps } from '@/lib/format'
import type {
  DnsBenchResult,
  DnsResult,
  HttpCheckResult,
  MacResult,
  PingResult,
  PortScanResult,
  SubnetResult,
  TcpResult,
  TlsResult,
  TraceResult,
} from '@/types'
import { useI18n, type TextKey } from '@/i18n/context'

const input =
  'h-8 min-w-0 flex-1 rounded-none border border-border bg-secondary px-2 font-mono text-xs outline-none focus:border-primary/60'

function useRunner<T>() {
  const [result, setResult] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [ms, setMs] = useState<number | null>(null)
  const run = async (fn: () => Promise<T>) => {
    setBusy(true)
    setError(null)
    const start = performance.now()
    try {
      setResult(await fn())
    } catch (e) {
      setResult(null)
      setError((e as Error).message)
    } finally {
      setMs(performance.now() - start)
      setBusy(false)
    }
  }
  return { result, error, busy, ms, run }
}

function ToolCard({
  title,
  desc,
  busy,
  error,
  ms,
  onRun,
  children,
  form,
}: {
  title: TextKey
  desc: TextKey
  busy: boolean
  error: string | null
  ms: number | null
  onRun: () => void
  form: React.ReactNode
  children?: React.ReactNode
}) {
  const { t } = useI18n()
  return (
    <GlassPanel title={t(title)} meta={ms != null && !busy ? t('toolTook', fmtMs(ms)) : undefined}>
      <p className="mb-3 text-xs text-muted-foreground">{t(desc)}</p>
      <form
        className="flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (!busy) onRun()
        }}
      >
        {form}
        <button
          type="submit"
          disabled={busy}
          className="press flex h-8 items-center gap-1.5 rounded-none bg-primary px-3 font-mono text-[11px] font-bold uppercase tracking-wider text-primary-foreground disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          {busy ? t('toolRunning') : t('toolRun')}
        </button>
      </form>
      {error && <p className="mt-3 border-l-2 border-destructive pl-2 font-mono text-xs text-destructive">{error}</p>}
      {children && <div className="mt-3 font-mono text-xs">{children}</div>}
    </GlassPanel>
  )
}

function Bar({ value, max, cls = 'bg-primary' }: { value: number | null; max: number; cls?: string }) {
  return (
    <span className="block h-1.5 w-full bg-white/[0.06]">
      <span className={`block h-full ${value == null ? '' : cls}`} style={{ width: `${value == null || max <= 0 ? 0 : Math.max(2, (value / max) * 100)}%` }} />
    </span>
  )
}

function KV({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(110px,auto)_1fr] gap-x-3 gap-y-0.5">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="min-w-0 break-words">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

function PingTool() {
  const [target, setTarget] = useState('1.1.1.1')
  const [count, setCount] = useState(10)
  const r = useRunner<PingResult>()
  const max = Math.max(1, ...(r.result?.rtts_ms.filter((v): v is number => v != null) ?? [1]))
  return (
    <ToolCard
      title="toolPing"
      desc="toolPingDesc"
      {...r}
      onRun={() => r.run(() => api.tools.ping(target, count))}
      form={
        <>
          <input className={input} value={target} onChange={(e) => setTarget(e.target.value)} aria-label="target" />
          <input className={`${input} max-w-[70px] flex-none`} type="number" min={1} max={50} value={count} onChange={(e) => setCount(Number(e.target.value))} aria-label="count" />
        </>
      }
    >
      {r.result && (
        <>
          <KV
            rows={[
              ['IP', `${r.result.ip}${r.result.dns_ms ? ` (DNS ${fmtMs(r.result.dns_ms)})` : ''}`],
              ['min / avg / max', `${fmtMs(r.result.min_ms)} / ${fmtMs(r.result.avg_ms)} / ${fmtMs(r.result.max_ms)}`],
              ['stddev · jitter', `${fmtMs(r.result.stddev_ms)} · ${fmtMs(r.result.jitter_ms)}`],
              ['loss', <span className={r.result.loss_pct ? 'text-warn' : 'text-ok'}>{r.result.loss_pct} %</span>],
            ]}
          />
          <div className="mt-2 flex h-10 items-end gap-[3px]">
            {r.result.rtts_ms.map((v, i) => (
              <span
                key={i}
                title={v == null ? `#${i + 1} timeout` : `#${i + 1} ${fmtMs(v)}`}
                className={`flex-1 ${v == null ? 'h-full bg-destructive/40' : 'bg-primary/80'}`}
                style={v == null ? undefined : { height: `${Math.max(6, (v / max) * 100)}%` }}
              />
            ))}
          </div>
        </>
      )}
    </ToolCard>
  )
}

function TraceTool() {
  const [target, setTarget] = useState('1.1.1.1')
  const r = useRunner<TraceResult>()
  const max = Math.max(1, ...(r.result?.hops.map((h) => h.rtt_ms ?? 0) ?? [1]))
  return (
    <ToolCard title="toolTrace" desc="toolTraceDesc" {...r} onRun={() => r.run(() => api.tools.traceroute(target))} form={<input className={input} value={target} onChange={(e) => setTarget(e.target.value)} aria-label="target" />}>
      {r.result && (
        <table className="w-full">
          <tbody>
            {r.result.hops.map((h) => (
              <tr key={h.ttl} className="border-b border-border/30">
                <td className="w-7 py-0.5 text-muted-foreground">{h.ttl}</td>
                <td className="truncate">{h.ip ?? '*'}{h.host ? <span className="text-muted-foreground"> {h.host}</span> : ''}</td>
                <td className="w-20 text-right">{fmtMs(h.rtt_ms)}</td>
                <td className="w-28 pl-2"><Bar value={h.rtt_ms} max={max} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </ToolCard>
  )
}

function DnsTool() {
  const [name, setName] = useState('example.com')
  const [type, setType] = useState('A')
  const [server, setServer] = useState('1.1.1.1')
  const r = useRunner<DnsResult>()
  return (
    <ToolCard
      title="toolDns"
      desc="toolDnsDesc"
      {...r}
      onRun={() => r.run(() => api.tools.dns(name, type, server))}
      form={
        <>
          <input className={input} value={name} onChange={(e) => setName(e.target.value)} aria-label="name" />
          <select className={`${input} max-w-[90px] flex-none`} value={type} onChange={(e) => setType(e.target.value)} aria-label="type">
            {['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SOA', 'PTR', 'SRV', 'CAA'].map((q) => (
              <option key={q}>{q}</option>
            ))}
          </select>
          <input className={`${input} max-w-[130px]`} value={server} onChange={(e) => setServer(e.target.value)} aria-label="server" />
        </>
      }
    >
      {r.result && (
        <>
          <p>
            <span className={r.result.rcode === 'NOERROR' ? 'text-ok' : 'text-warn'}>{r.result.rcode}</span> · {fmtMs(r.result.ms)} · @{r.result.server}
            {r.result.authoritative ? ' · AA' : ''}
            {r.result.truncated ? ' · TC' : ''}
          </p>
          {r.result.answers.map((a, i) => (
            <p key={i} className="break-all">
              <span className="text-muted-foreground">{a.name} {a.ttl_s}s {a.type}</span> {a.data}
            </p>
          ))}
        </>
      )}
    </ToolCard>
  )
}

function DnsBenchTool() {
  const [name, setName] = useState('example.com')
  const r = useRunner<DnsBenchResult>()
  const max = Math.max(1, ...(r.result?.results.map((x) => x.median_ms ?? 0) ?? [1]))
  return (
    <ToolCard title="toolDnsBench" desc="toolDnsBenchDesc" {...r} onRun={() => r.run(() => api.tools.dnsBench(name))} form={<input className={input} value={name} onChange={(e) => setName(e.target.value)} aria-label="name" />}>
      {r.result && (
        <table className="w-full">
          <tbody>
            {r.result.results.map((x, i) => (
              <tr key={x.server} className="border-b border-border/30">
                <td className="py-0.5">{i === 0 && x.median_ms != null ? '🏁 ' : ''}{x.server}</td>
                <td className="w-24 text-right">{fmtMs(x.median_ms)}</td>
                <td className="w-16 text-right text-muted-foreground">{x.answered}/{x.rounds}</td>
                <td className="w-28 pl-2"><Bar value={x.median_ms} max={max} cls={i === 0 ? 'bg-ok' : 'bg-primary'} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </ToolCard>
  )
}

function TcpTool() {
  const [target, setTarget] = useState('192.168.1.1')
  const [port, setPort] = useState(443)
  const r = useRunner<TcpResult>()
  return (
    <ToolCard
      title="toolTcp"
      desc="toolTcpDesc"
      {...r}
      onRun={() => r.run(() => api.tools.tcp(target, port))}
      form={
        <>
          <input className={input} value={target} onChange={(e) => setTarget(e.target.value)} aria-label="target" />
          <input className={`${input} max-w-[80px] flex-none`} type="number" min={1} max={65535} value={port} onChange={(e) => setPort(Number(e.target.value))} aria-label="port" />
        </>
      }
    >
      {r.result && (
        <KV
          rows={[
            ['state', <span className={r.result.open ? 'text-ok' : 'text-destructive'}>{r.result.open ? 'open' : 'closed/filtered'}</span>],
            ['connect', r.result.connect_ms.map((v) => fmtMs(v)).join(' · ')],
            ['avg', fmtMs(r.result.avg_ms)],
            ['banner', r.result.banner || '—'],
          ]}
        />
      )}
    </ToolCard>
  )
}

function PortScanTool() {
  const [target, setTarget] = useState('192.168.1.1')
  const [ports, setPorts] = useState('')
  const r = useRunner<PortScanResult>()
  const { t } = useI18n()
  return (
    <ToolCard
      title="toolPortscan"
      desc="toolPortscanDesc"
      {...r}
      onRun={() => r.run(() => api.tools.portscan(target, ports))}
      form={
        <>
          <input className={`${input} max-w-[150px]`} value={target} onChange={(e) => setTarget(e.target.value)} aria-label="target" />
          <input className={input} value={ports} placeholder={t('toolPortsPlaceholder')} onChange={(e) => setPorts(e.target.value)} aria-label="ports" />
        </>
      }
    >
      {r.result && (
        <>
          <p className="text-muted-foreground">{t('toolPortsSummary', r.result.open.length, r.result.scanned)}</p>
          <div className="mt-1 flex flex-wrap gap-1">
            {r.result.open.map((p) => (
              <span key={p.port} className="border border-primary/40 bg-primary/[0.12] px-1.5 py-0.5 text-primary">
                {p.port} <span className="text-muted-foreground">{p.service}</span>
              </span>
            ))}
          </div>
        </>
      )}
    </ToolCard>
  )
}

const PHASES: { key: keyof HttpCheckResult['timing']; label: string; cls: string }[] = [
  { key: 'dns_ms', label: 'DNS', cls: 'bg-[#ffbe37]' },
  { key: 'connect_ms', label: 'TCP', cls: 'bg-[#36e09e]' },
  { key: 'tls_ms', label: 'TLS', cls: 'bg-[#c4a7ff]' },
  { key: 'ttfb_ms', label: 'TTFB', cls: 'bg-[#2de2e6]' },
  { key: 'transfer_ms', label: 'transfer', cls: 'bg-[#4cc9ff]' },
]

function HttpTool() {
  const [url, setUrl] = useState('https://one.one.one.one/')
  const r = useRunner<HttpCheckResult>()
  const total = r.result ? PHASES.reduce((n, p) => n + (r.result!.timing[p.key] ?? 0), 0) : 0
  return (
    <ToolCard title="toolHttp" desc="toolHttpDesc" {...r} onRun={() => r.run(() => api.tools.http(url))} form={<input className={input} value={url} onChange={(e) => setUrl(e.target.value)} aria-label="url" />}>
      {r.result && (
        <>
          <p>
            <span className={r.result.status != null && r.result.status < 400 ? 'text-ok' : 'text-destructive'}>
              {r.result.status != null ? `HTTP/${r.result.http_version} ${r.result.status} ` : ''}
              {r.result.reason}
            </span>{' '}
            · {r.result.ip} · {fmtBytes(r.result.body_bytes)}
            {r.result.truncated ? ' (truncated)' : ''}
            {r.result.tls_version ? ` · ${r.result.tls_version}` : ''}
            {r.result.throughput_mbps != null ? ` · ${fmtMbps(r.result.throughput_mbps)}` : ''}
          </p>
          <div className="mt-2 flex h-4 w-full overflow-hidden bg-white/[0.05]" title="waterfall">
            {PHASES.map((p) => {
              const v = r.result!.timing[p.key]
              if (v == null || total <= 0) return null
              return <span key={p.key} className={p.cls} style={{ width: `${(v / total) * 100}%` }} title={`${p.label} ${fmtMs(v)}`} />
            })}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 text-[11px]">
            {PHASES.map((p) => (
              <span key={p.key}>
                <span className={`mr-1 inline-block h-2 w-2 ${p.cls}`} />
                {p.label} {fmtMs(r.result!.timing[p.key])}
              </span>
            ))}
            <span className="font-semibold">total {fmtMs(r.result.timing.total_ms)}</span>
          </div>
          <div className="mt-2">
            <KV rows={Object.entries(r.result.headers).map(([k, v]) => [k, v])} />
          </div>
          {r.result.security_headers_missing.length > 0 && (
            <p className="mt-2 text-warn">missing: {r.result.security_headers_missing.join(', ')}</p>
          )}
        </>
      )}
    </ToolCard>
  )
}

function TlsTool() {
  const [target, setTarget] = useState('one.one.one.one')
  const [port, setPort] = useState(443)
  const r = useRunner<TlsResult>()
  return (
    <ToolCard
      title="toolTls"
      desc="toolTlsDesc"
      {...r}
      onRun={() => r.run(() => api.tools.tls(target, port))}
      form={
        <>
          <input className={input} value={target} onChange={(e) => setTarget(e.target.value)} aria-label="target" />
          <input className={`${input} max-w-[80px] flex-none`} type="number" value={port} onChange={(e) => setPort(Number(e.target.value))} aria-label="port" />
        </>
      }
    >
      {r.result && (
        <KV
          rows={[
            ['protocol', `${r.result.version} · ${r.result.cipher} (${r.result.cipher_bits} bit) · ALPN ${r.result.alpn ?? '—'}`],
            ['timing', `connect ${fmtMs(r.result.connect_ms)} · handshake ${fmtMs(r.result.handshake_ms)}`],
            ['trust', <span className={r.result.trusted ? 'text-ok' : 'text-warn'}>{r.result.trusted ? 'trusted (system store)' : r.result.trust_error}</span>],
            ['subject', r.result.certificate.subject],
            ['issuer', r.result.certificate.issuer],
            ['SAN', r.result.certificate.san.join(', ') || '—'],
            ['validity', `${r.result.certificate.not_before} → ${r.result.certificate.not_after} (${r.result.certificate.days_remaining ?? '?'} d left)`],
            ['key · sig', `${r.result.certificate.key ?? '?'} · ${r.result.certificate.signature_algorithm ?? '?'}`],
          ]}
        />
      )}
    </ToolCard>
  )
}

function SubnetTool() {
  const [cidr, setCidr] = useState('192.168.1.0/24')
  const r = useRunner<SubnetResult>()
  return (
    <ToolCard title="toolSubnet" desc="toolSubnetDesc" {...r} onRun={() => r.run(() => api.tools.subnet(cidr))} form={<input className={input} value={cidr} onChange={(e) => setCidr(e.target.value)} aria-label="cidr" />}>
      {r.result && (
        <KV
          rows={[
            ['network', r.result.cidr],
            ['netmask · wildcard', `${r.result.netmask} · ${r.result.wildcard}`],
            ['broadcast', r.result.broadcast ?? '—'],
            ['hosts', `${r.result.first_host} – ${r.result.last_host} (${r.result.usable_hosts.toLocaleString()} usable / ${r.result.addresses.toLocaleString()} addresses)`],
            ['private', r.result.private ? 'yes (RFC 1918)' : 'no'],
          ]}
        />
      )}
    </ToolCard>
  )
}

function MacTool() {
  const [mac, setMac] = useState('')
  const r = useRunner<MacResult>()
  return (
    <ToolCard title="toolMac" desc="toolMacDesc" {...r} onRun={() => r.run(() => api.tools.mac(mac))} form={<input className={input} value={mac} placeholder="aa:bb:cc:dd:ee:ff" onChange={(e) => setMac(e.target.value)} aria-label="mac" />}>
      {r.result && (
        <KV
          rows={[
            ['MAC · OUI', `${r.result.mac} · ${r.result.oui}`],
            ['vendor', r.result.vendor || '— (not in the OUI registry)'],
            ['locally administered', r.result.locally_administered ? 'yes' : 'no'],
            ['randomized', r.result.randomized ? 'yes — private Wi-Fi address (phone/tablet/PC)' : 'no'],
            ['virtual platform', r.result.virtual_platform || '—'],
          ]}
        />
      )}
    </ToolCard>
  )
}

/** Diagnostics run *from the NetScan host*. Each tool streams its progress
 *  to the terminal dock (filter "tools") as it runs. */
export default function Toolbox() {
  const { t } = useI18n()
  return (
    <div className="space-y-[18px]">
      <p className="glass px-4 py-3 font-mono text-xs text-muted-foreground">{t('toolsIntro')}</p>
      <div className="grid gap-[18px] lg:grid-cols-2">
        <PingTool />
        <TraceTool />
        <HttpTool />
        <TlsTool />
        <DnsTool />
        <DnsBenchTool />
        <TcpTool />
        <PortScanTool />
        <SubnetTool />
        <MacTool />
      </div>
    </div>
  )
}
