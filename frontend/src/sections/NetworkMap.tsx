import { useMemo, useRef, useState } from 'react'
import { Minus, Plus, RotateCcw } from 'lucide-react'
import { GlassPanel } from '@/components/metrics'
import { RoleIcon } from '@/components/RoleIcon'
import { ROLE_COLOR } from '@/lib/roles'
import { usePoll } from '@/hooks/useNetscan'
import { api } from '@/lib/api'
import { openDeviceDetail } from '@/lib/deviceDetail'
import { fmtMs } from '@/lib/format'
import type { DeviceRole, MapNode } from '@/types'
import PanelError from './PanelError'
import IpMap from './IpMap'
import { useI18n } from '@/i18n/context'

const W = 1000
const H = 660
const CX = W / 2
const CY = H / 2
const R_MIN = 70
const R_MAX = 290
const R_OFFLINE = 312
// RTT → radius on a log scale: 0.1 ms sits by the gateway, 200 ms at the rim.
const RTT_LO = 0.1
const RTT_HI = 200
const GUIDES = [0.5, 1, 5, 20, 100]

function radiusFor(rtt: number | null, online: boolean): number {
  if (!online || rtt == null) return R_OFFLINE
  const x = Math.min(Math.max(rtt, RTT_LO), RTT_HI)
  const f = Math.log(x / RTT_LO) / Math.log(RTT_HI / RTT_LO)
  return R_MIN + f * (R_MAX - R_MIN)
}

const ROLE_ORDER: DeviceRole[] = [
  'netscan',
  'network',
  'hypervisor',
  'vm',
  'server',
  'nas',
  'workstation',
  'mobile',
  'media',
  'iot',
  'camera',
  'printer',
  'unknown',
]

function ipNum(ip: string): number {
  return ip.split('.').reduce((n, o) => n * 256 + Number(o), 0)
}

interface Placed extends MapNode {
  x: number
  y: number
  r: number
}

function layout(nodes: MapNode[]): { centre: Placed | null; placed: Placed[] } {
  const centreNode = nodes.find((n) => n.role === 'gateway') ?? null
  const rest = nodes.filter((n) => n !== centreNode)
  const byRole = new Map<DeviceRole, MapNode[]>()
  for (const n of rest) byRole.set(n.role, [...(byRole.get(n.role) ?? []), n])
  const roles = [...byRole.keys()].sort((a, b) => ROLE_ORDER.indexOf(a) - ROLE_ORDER.indexOf(b))
  const total = rest.length || 1
  const placed: Placed[] = []
  let angle = -Math.PI / 2
  for (const role of roles) {
    const members = (byRole.get(role) ?? []).sort((a, b) => ipNum(a.ip) - ipNum(b.ip))
    // Each role gets a sector proportional to its size (min. one slot).
    const sector = (Math.max(members.length, 1) / total) * Math.PI * 2
    members.forEach((n, i) => {
      const a = angle + (sector * (i + 0.5)) / members.length
      const r = radiusFor(n.latency_ms, n.online)
      placed.push({ ...n, r, x: CX + r * Math.cos(a), y: CY + r * Math.sin(a) })
    })
    angle += sector
  }
  const centre = centreNode ? { ...centreNode, r: 0, x: CX, y: CY } : null
  return { centre, placed }
}

const TONE_STROKE = (n: MapNode) =>
  !n.online ? '#5b6573' : n.latency_ms == null ? '#82909c' : n.latency_ms < 5 ? '#36e09e' : n.latency_ms < 30 ? '#ffbe37' : '#ff4a5e'

/** Latency radar: the gateway at the centre, every device at a distance
 *  proportional to its live RTT (log scale), grouped in sectors by inferred
 *  role. Colour = role, ring = risk, dashed = offline, red dot = untrusted. */
export default function NetworkMap() {
  const { t } = useI18n()
  const { data, error, refresh } = usePoll(api.map, 10000)
  const [hover, setHover] = useState<Placed | null>(null)
  const [focusRole, setFocusRole] = useState<DeviceRole | null>(null)
  const [labels, setLabels] = useState<'name' | 'ip' | 'none'>('name')
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const { centre, placed } = useMemo(() => layout(data?.nodes ?? []), [data])
  const roles = useMemo(
    () => Object.entries(data?.roles ?? {}).sort((a, b) => b[1] - a[1]) as [DeviceRole, number][],
    [data],
  )

  const toSvg = (dx: number, dy: number) => {
    const el = svgRef.current
    if (!el) return { x: dx, y: dy }
    const scale = W / el.clientWidth
    return { x: dx * scale, y: dy * scale }
  }

  const all = centre ? [centre, ...placed] : placed
  const label = (n: Placed) => (labels === 'ip' ? n.ip : labels === 'name' ? (n.name.length > 18 ? `${n.name.slice(0, 17)}…` : n.name) : '')

  return (
    <div className="space-y-[18px]">
      <GlassPanel
        title={t('mapTitle')}
        right={
          <div className="flex flex-wrap items-center justify-end gap-1.5 font-mono text-[10.5px]">
            {(['name', 'ip', 'none'] as const).map((l) => (
              <button
                key={l}
                onClick={() => setLabels(l)}
                className={`border px-2 py-0.5 uppercase tracking-wider ${labels === l ? 'border-primary/60 bg-primary/[0.12] text-primary' : 'border-border text-muted-foreground'}`}
              >
                {t(l === 'name' ? 'mapLabelName' : l === 'ip' ? 'mapLabelIp' : 'mapLabelNone')}
              </button>
            ))}
            <span className="mx-1 h-4 w-px bg-border" />
            <button className="border border-border p-1 text-muted-foreground hover:text-foreground" onClick={() => setZoom((z) => Math.min(z * 1.25, 4))} aria-label="zoom in">
              <Plus className="h-3 w-3" />
            </button>
            <button className="border border-border p-1 text-muted-foreground hover:text-foreground" onClick={() => setZoom((z) => Math.max(z / 1.25, 0.5))} aria-label="zoom out">
              <Minus className="h-3 w-3" />
            </button>
            <button
              className="border border-border p-1 text-muted-foreground hover:text-foreground"
              onClick={() => {
                setZoom(1)
                setPan({ x: 0, y: 0 })
              }}
              aria-label="reset view"
            >
              <RotateCcw className="h-3 w-3" />
            </button>
          </div>
        }
      >
        <PanelError error={error} onRetry={refresh} />
        <div className="flex flex-wrap gap-1.5 pb-3">
          {roles.map(([role, n]) => (
            <button
              key={role}
              onClick={() => setFocusRole((r) => (r === role ? null : role))}
              className={`flex items-center gap-1.5 border px-2 py-1 font-mono text-[10.5px] transition-colors ${focusRole === role ? 'border-primary/60 bg-primary/[0.1]' : 'border-border hover:border-primary/40'}`}
            >
              <RoleIcon role={role} className="h-3 w-3" />
              {t('role', role)} <span className="text-muted-foreground">{n}</span>
            </button>
          ))}
        </div>
        {all.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">{t('mapEmpty')}</p>
        ) : (
          <div className="relative overflow-hidden border border-border/60 bg-[radial-gradient(circle_at_center,rgba(45,226,230,0.05),transparent_65%)]">
            <svg
              ref={svgRef}
              viewBox={`0 0 ${W} ${H}`}
              className="h-[min(66vh,620px)] w-full cursor-grab touch-none select-none active:cursor-grabbing"
              onWheel={(e) => setZoom((z) => Math.min(Math.max(z * (e.deltaY < 0 ? 1.1 : 1 / 1.1), 0.5), 4))}
              onPointerDown={(e) => {
                drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y }
                ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
              }}
              onPointerMove={(e) => {
                if (!drag.current) return
                const d = toSvg(e.clientX - drag.current.x, e.clientY - drag.current.y)
                setPan({ x: drag.current.px + d.x / zoom, y: drag.current.py + d.y / zoom })
              }}
              onPointerUp={() => (drag.current = null)}
              role="img"
              aria-label={t('mapAria', all.length)}
            >
              <g transform={`translate(${CX} ${CY}) scale(${zoom}) translate(${-CX + pan.x} ${-CY + pan.y})`}>
                {GUIDES.map((ms) => {
                  const r = radiusFor(ms, true)
                  return (
                    <g key={ms}>
                      <circle cx={CX} cy={CY} r={r} fill="none" stroke="rgba(120,200,210,0.09)" strokeDasharray="2 5" />
                      <text x={CX + 4} y={CY - r - 3} fill="rgba(233,236,241,0.32)" fontSize={10} fontFamily="JetBrains Mono">
                        {ms} ms
                      </text>
                    </g>
                  )
                })}
                <circle cx={CX} cy={CY} r={R_OFFLINE} fill="none" stroke="rgba(255,74,94,0.18)" strokeDasharray="4 6" />
                <text x={CX + 4} y={CY - R_OFFLINE - 3} fill="rgba(255,74,94,0.45)" fontSize={10} fontFamily="JetBrains Mono">
                  {t('mapOfflineRing')}
                </text>

                {centre &&
                  placed.map((n) => (
                    <line
                      key={`e-${n.id}`}
                      x1={CX}
                      y1={CY}
                      x2={n.x}
                      y2={n.y}
                      stroke={TONE_STROKE(n)}
                      strokeOpacity={focusRole && n.role !== focusRole ? 0.05 : n.online ? 0.28 : 0.12}
                      strokeDasharray={n.online ? undefined : '3 4'}
                    />
                  ))}

                {all.map((n) => {
                  const dim = focusRole != null && n.role !== focusRole && n !== centre
                  const size = n === centre ? 16 : 7 + Math.min(n.ports.length, 10) * 0.7
                  const color = ROLE_COLOR[n.role] ?? '#82909c'
                  const risky = n.risk_level === 'high' || n.risk_level === 'critical'
                  return (
                    <g
                      key={n.id}
                      transform={`translate(${n.x} ${n.y})`}
                      opacity={dim ? 0.18 : n.online ? 1 : 0.55}
                      className="cursor-pointer"
                      onPointerEnter={() => setHover(n)}
                      onPointerLeave={() => setHover((h) => (h?.id === n.id ? null : h))}
                      onClick={(e) => {
                        e.stopPropagation()
                        if (n.mac) openDeviceDetail(n.mac)
                      }}
                    >
                      {risky && (
                        <circle r={size + 6} fill="none" stroke={n.risk_level === 'critical' ? '#ff4a5e' : '#ffbe37'} strokeWidth={1.5} strokeOpacity={0.8}>
                          <animate attributeName="r" values={`${size + 4};${size + 9};${size + 4}`} dur="2.4s" repeatCount="indefinite" />
                        </circle>
                      )}
                      <circle
                        r={size}
                        fill={color}
                        fillOpacity={0.2}
                        stroke={color}
                        strokeWidth={hover?.id === n.id ? 2.5 : 1.5}
                        strokeDasharray={n.online ? undefined : '3 3'}
                      />
                      {!n.trusted && n !== centre && <circle cx={size * 0.75} cy={-size * 0.75} r={3} fill="#ff4a5e" />}
                      {labels !== 'none' && (
                        <text
                          y={size + 12}
                          textAnchor="middle"
                          fontSize={n === centre ? 12 : 10}
                          fontFamily="JetBrains Mono"
                          fill={n.online ? 'rgba(233,236,241,0.85)' : 'rgba(233,236,241,0.45)'}
                        >
                          {label(n)}
                        </text>
                      )}
                    </g>
                  )
                })}
              </g>
            </svg>
            {hover && (
              <div className="pointer-events-none absolute left-3 top-3 w-[280px] border border-primary/40 bg-[rgba(11,13,17,0.96)] p-3 font-mono text-[11px] shadow-hard-lg">
                <div className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
                  <RoleIcon role={hover.role} />
                  <span className="truncate">{hover.name}</span>
                </div>
                <div className="mt-1 text-muted-foreground">
                  {hover.ip}
                  {hover.mac ? ` · ${hover.mac}` : ''}
                </div>
                <div className="text-muted-foreground">{hover.vendor || '—'}{hover.virtual ? ` · ${hover.virtual}` : ''}{hover.randomized_mac ? ` · ${t('mapRandomMac')}` : ''}</div>
                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5">
                  <dt className="text-muted-foreground">{t('mapState')}</dt>
                  <dd className={hover.online ? 'text-ok' : 'text-destructive'}>
                    {hover.online ? 'up' : 'down'}
                    {hover.method ? ` · ${hover.method}` : ''}
                  </dd>
                  <dt className="text-muted-foreground">RTT</dt>
                  <dd>{fmtMs(hover.latency_ms)}</dd>
                  <dt className="text-muted-foreground">{t('mapRole')}</dt>
                  <dd>{t('role', hover.role)}</dd>
                  <dt className="text-muted-foreground">{t('mapRisk')}</dt>
                  <dd className={hover.risk_level === 'low' ? 'text-ok' : hover.risk_level === 'medium' ? 'text-warn' : 'text-destructive'}>
                    {hover.risk_score}/100 · {t('riskLevel', hover.risk_level)}
                  </dd>
                  <dt className="text-muted-foreground">{t('colPorts')}</dt>
                  <dd className="truncate">{hover.ports.join(', ') || '—'}</dd>
                </dl>
                <p className="mt-2 text-[10px] leading-snug text-muted-foreground">{hover.role_reasons.join(' · ')}</p>
              </div>
            )}
          </div>
        )}
        <p className="mt-2 font-mono text-[10.5px] leading-relaxed text-muted-foreground">{t('mapLegend')}</p>
      </GlassPanel>
      <IpMap />
    </div>
  )
}
