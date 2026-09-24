import { lazy, Suspense, useCallback, useState } from 'react'
import { Activity, BarChart3, LayoutDashboard, Network, Plug, Radio } from 'lucide-react'
import TokenDialog from '@/components/TokenDialog'
import HeroTitle from '@/components/HeroTitle'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import Header from '@/sections/Header'
import StatCards from '@/sections/StatCards'
import DevicesTable from '@/sections/DevicesTable'
import AlertsFeed from '@/sections/AlertsFeed'
import CapabilitiesBar from '@/sections/CapabilitiesBar'
import SystemStatus from '@/sections/SystemStatus'
import LogConsole from '@/sections/LogConsole'
import { Skeleton } from '@/components/ui/skeleton'
import { useI18n } from '@/i18n/context'

// Lazy-loaded so the chart-heavy Analytics tab (Recharts) and the large
// Integrations panel are code-split out of the initial bundle — the shell and
// the default tab load without them, and they arrive when their tab is opened.
const LiveView = lazy(() => import('@/sections/LiveView'))
const AnalyticsPanel = lazy(() => import('@/sections/AnalyticsPanel'))
const TrendsPanel = lazy(() => import('@/sections/TrendsPanel'))
const ServicesPanel = lazy(() => import('@/sections/ServicesPanel'))
const Integrations = lazy(() => import('@/sections/Integrations'))

const TABS = [
  { value: 'live', labelKey: 'tabLive', icon: Radio },
  { value: 'resumen', labelKey: 'tabOverview', icon: LayoutDashboard },
  { value: 'dispositivos', labelKey: 'tabDevices', icon: Network },
  { value: 'analitica', labelKey: 'tabAnalytics', icon: BarChart3 },
  { value: 'integraciones', labelKey: 'tabIntegrations', icon: Plug },
  { value: 'sistema', labelKey: 'tabSystem', icon: Activity },
] as const

// Fade + slide the active tab panel in on mount. Only the active tab's panels
// are mounted (Radix unmounts the rest), so this fires on every switch — and
// it means only the visible section polls the API, not all of them at once.
const PANEL_ANIM = 'animate-in fade-in-50 slide-in-from-bottom-1 duration-300 space-y-[18px]'

function PanelFallback() {
  return (
    <div className="glass p-5">
      <Skeleton className="h-48 w-full" />
    </div>
  )
}

export default function Home() {
  const { t } = useI18n()
  // Bumped when a scan finishes so the mounted panels re-poll.
  const [refreshKey, setRefreshKey] = useState(0)
  const bump = useCallback(() => setRefreshKey((k) => k + 1), [])

  // Remember the last section across reloads (per-viewer convenience).
  const [tab, setTab] = useState(() => {
    try {
      return localStorage.getItem('netscan_tab') || 'live'
    } catch {
      return 'resumen'
    }
  })
  const onTab = useCallback((v: string) => {
    setTab(v)
    try {
      localStorage.setItem('netscan_tab', v)
    } catch {
      /* private mode / storage disabled — the tab just won't persist */
    }
  }, [])

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-background text-foreground">
      <TokenDialog />
      {/* Sober, STATIC background: a flat ink plate plus a single soft cyan
          glow at the top. No grid, no scanlines, no blur filters, no animation —
          the compositor paints these once and never touches them again. */}
      <div className="app-bg" aria-hidden="true" />
      <div className="app-glow" aria-hidden="true" />

      <div className="relative z-10 mx-auto max-w-[1560px] px-4 pb-14 pt-7 sm:px-6">
        <HeroTitle />
        <Header onScanDone={bump} />

        <Tabs value={tab} onValueChange={onTab} className="mt-5 gap-4">
          <TabsList className="glass hud relative grid h-auto w-full grid-cols-3 gap-0 rounded-none border border-border bg-card p-0 sm:grid-cols-6">
            {TABS.map(({ value, labelKey, icon: Icon }, i) => (
              <TabsTrigger
                key={value}
                value={value}
                className="group relative flex items-center justify-center gap-2 rounded-none border-r border-border/70 px-2 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground transition-colors last:border-r-0 data-[state=active]:bg-primary/[0.07] data-[state=active]:text-primary sm:justify-start sm:text-xs"
              >
                {/* active top ticker */}
                <span className="pointer-events-none absolute inset-x-0 top-0 h-[2px] scale-x-0 bg-primary transition-transform duration-150 group-data-[state=active]:scale-x-100" />
                <span className="hidden font-mono text-[9.5px] tabular-nums text-muted-foreground/60 group-data-[state=active]:text-primary/70 lg:inline">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <Icon className="h-4 w-4 shrink-0" />
                <span className="hidden sm:inline">{t(labelKey)}</span>
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="live" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <LiveView />
            </Suspense>
          </TabsContent>

          <TabsContent value="resumen" className={PANEL_ANIM}>
            <StatCards refreshKey={refreshKey} />
            <div className="grid gap-[18px] xl:grid-cols-[1.35fr_1fr]">
              <SystemStatus />
              <AlertsFeed refreshKey={refreshKey} />
            </div>
          </TabsContent>

          <TabsContent value="dispositivos" className={PANEL_ANIM}>
            <DevicesTable refreshKey={refreshKey} />
          </TabsContent>

          <TabsContent value="analitica" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <TrendsPanel refreshKey={refreshKey} />
              <AnalyticsPanel refreshKey={refreshKey} />
              <ServicesPanel refreshKey={refreshKey} />
            </Suspense>
          </TabsContent>

          <TabsContent value="integraciones" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <Integrations />
            </Suspense>
          </TabsContent>

          <TabsContent value="sistema" className={PANEL_ANIM}>
            <div className="grid gap-[18px] lg:grid-cols-2">
              <CapabilitiesBar />
              <LogConsole />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
