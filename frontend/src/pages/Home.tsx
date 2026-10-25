import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { Activity, BarChart3, LayoutDashboard, Network, Plug, Radio, Share2, ShieldAlert, Wrench } from 'lucide-react'
import TokenDialog from '@/components/TokenDialog'
import HeroTitle from '@/components/HeroTitle'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import Header from '@/sections/Header'
import { Skeleton } from '@/components/ui/skeleton'
import { useI18n } from '@/i18n/context'
import { logFront } from '@/lib/telemetry'
import { api } from '@/lib/api'
import { startTour, tourSeen, useTourOpen } from '@/lib/tour'
import { toast } from 'sonner'

// Every tab is lazy-loaded: the initial bundle is the shell (header,
// terminal dock, token dialog) and each section arrives when its tab opens.
const StatCards = lazy(() => import('@/sections/StatCards'))
const DevicesTable = lazy(() => import('@/sections/DevicesTable'))
const AlertsFeed = lazy(() => import('@/sections/AlertsFeed'))
const CapabilitiesBar = lazy(() => import('@/sections/CapabilitiesBar'))
const SystemStatus = lazy(() => import('@/sections/SystemStatus'))
const LogConsole = lazy(() => import('@/sections/LogConsole'))
const TerminalDock = lazy(() => import('@/sections/TerminalDock'))
const LiveView = lazy(() => import('@/sections/LiveView'))
const AnalyticsPanel = lazy(() => import('@/sections/AnalyticsPanel'))
const TrendsPanel = lazy(() => import('@/sections/TrendsPanel'))
const ServicesPanel = lazy(() => import('@/sections/ServicesPanel'))
const Integrations = lazy(() => import('@/sections/Integrations'))
const NetworkMap = lazy(() => import('@/sections/NetworkMap'))
const SecurityPanel = lazy(() => import('@/sections/SecurityPanel'))
const Toolbox = lazy(() => import('@/sections/Toolbox'))
const DeviceDetailHost = lazy(() => import('@/sections/DeviceDetailDialog'))
const Tour = lazy(() => import('@/sections/Tour'))

const TABS = [
  { value: 'live', labelKey: 'tabLive', icon: Radio },
  { value: 'resumen', labelKey: 'tabOverview', icon: LayoutDashboard },
  { value: 'dispositivos', labelKey: 'tabDevices', icon: Network },
  { value: 'mapa', labelKey: 'tabMap', icon: Share2 },
  { value: 'seguridad', labelKey: 'tabSecurity', icon: ShieldAlert },
  { value: 'analitica', labelKey: 'tabAnalytics', icon: BarChart3 },
  { value: 'herramientas', labelKey: 'tabTools', icon: Wrench },
  { value: 'integraciones', labelKey: 'tabIntegrations', icon: Plug },
  { value: 'sistema', labelKey: 'tabSystem', icon: Activity },
] as const

const TAB_VALUES: readonly string[] = TABS.map((t) => t.value)

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

  // Remember the last section across reloads (per-viewer convenience). A
  // stored value from an older version that no longer exists falls back to Live.
  const [tab, setTab] = useState(() => {
    try {
      const saved = localStorage.getItem('netscan_tab') || 'live'
      return TAB_VALUES.includes(saved) ? saved : 'live'
    } catch {
      return 'live'
    }
  })
  const onTab = useCallback((v: string) => {
    setTab(v)
    logFront('ui', `tab → ${v}`, 'debug')
    try {
      localStorage.setItem('netscan_tab', v)
    } catch {
      /* private mode / storage disabled — the tab just won't persist */
    }
  }, [])

  // First visit: open the guided tour once the shell has painted — unless a
  // dialog (the API-token prompt) is already asking for attention.
  const tourOpen = useTourOpen()
  useEffect(() => {
    if (tourSeen()) return
    const id = setTimeout(() => {
      if (!document.querySelector('[role="dialog"]')) startTour()
    }, 1200)
    return () => clearTimeout(id)
  }, [])
  const startFirstScan = useCallback(() => {
    api.startScan({}).catch((e: Error) => toast.error(t('toastScanStartFailed'), { description: e.message }))
  }, [t])

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-background text-foreground">
      <TokenDialog />
      {/* Sober, STATIC background: a flat ink plate plus a single soft cyan
          glow at the top. No grid, no scanlines, no blur filters, no animation —
          the compositor paints these once and never touches them again. */}
      <div className="app-bg" aria-hidden="true" />
      <div className="app-glow" aria-hidden="true" />

      <div className="relative z-10 mx-auto max-w-[1560px] px-4 pb-6 pt-7 sm:px-6">
        <HeroTitle />
        <Header onScanDone={bump} onNavigate={onTab} />

        <Tabs value={tab} onValueChange={onTab} className="mt-5 gap-4">
          <TabsList data-tour="tabs" className="glass hud relative grid h-auto w-full grid-cols-3 gap-0 rounded-none border border-border bg-card p-0 sm:grid-cols-5 xl:grid-cols-9">
            {TABS.map(({ value, labelKey, icon: Icon }, i) => (
              <TabsTrigger
                key={value}
                value={value}
                data-tour={`tab-${value}`}
                className="group relative flex items-center justify-center gap-2 rounded-none border-r border-b border-border/70 px-2 py-3 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground transition-colors data-[state=active]:bg-primary/[0.07] data-[state=active]:text-primary xl:border-b-0 xl:last:border-r-0"
              >
                {/* active top ticker */}
                <span className="pointer-events-none absolute inset-x-0 top-0 h-[2px] scale-x-0 bg-primary transition-transform duration-150 group-data-[state=active]:scale-x-100" />
                <span className="hidden font-mono text-[9.5px] tabular-nums text-muted-foreground/60 group-data-[state=active]:text-primary/70 2xl:inline">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <Icon className="h-4 w-4 shrink-0" />
                <span className="hidden truncate sm:inline">{t(labelKey)}</span>
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="live" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <LiveView />
            </Suspense>
          </TabsContent>

          <TabsContent value="resumen" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <StatCards refreshKey={refreshKey} />
              <div className="grid gap-[18px] xl:grid-cols-[1.35fr_1fr]">
                <SystemStatus />
                <AlertsFeed refreshKey={refreshKey} />
              </div>
            </Suspense>
          </TabsContent>

          <TabsContent value="dispositivos" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <DevicesTable refreshKey={refreshKey} />
            </Suspense>
          </TabsContent>

          <TabsContent value="mapa" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <NetworkMap />
            </Suspense>
          </TabsContent>

          <TabsContent value="seguridad" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <SecurityPanel />
            </Suspense>
          </TabsContent>

          <TabsContent value="analitica" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <TrendsPanel refreshKey={refreshKey} />
              <AnalyticsPanel refreshKey={refreshKey} />
              <ServicesPanel refreshKey={refreshKey} />
            </Suspense>
          </TabsContent>

          <TabsContent value="herramientas" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <Toolbox />
            </Suspense>
          </TabsContent>

          <TabsContent value="integraciones" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <Integrations />
            </Suspense>
          </TabsContent>

          <TabsContent value="sistema" className={PANEL_ANIM}>
            <Suspense fallback={<PanelFallback />}>
              <div className="grid gap-[18px] lg:grid-cols-2">
                <CapabilitiesBar />
                <LogConsole />
              </div>
            </Suspense>
          </TabsContent>
        </Tabs>
      </div>

      <Suspense fallback={null}>
        <DeviceDetailHost />
        <TerminalDock />
        {tourOpen && <Tour onNavigate={onTab} onStartScan={startFirstScan} />}
      </Suspense>
    </div>
  )
}
