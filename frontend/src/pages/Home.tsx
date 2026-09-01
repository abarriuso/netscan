import { lazy, Suspense, useCallback, useState } from 'react'
import { Activity, BarChart3, LayoutDashboard, Network, Plug } from 'lucide-react'
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

// Lazy-loaded so the chart-heavy Analytics tab (Recharts) and the large
// Integrations panel are code-split out of the initial bundle — the shell and
// the default tab load without them, and they arrive when their tab is opened.
const AnalyticsPanel = lazy(() => import('@/sections/AnalyticsPanel'))
const TrendsPanel = lazy(() => import('@/sections/TrendsPanel'))
const ServicesPanel = lazy(() => import('@/sections/ServicesPanel'))
const Integrations = lazy(() => import('@/sections/Integrations'))

const TABS = [
  { value: 'resumen', label: 'Resumen', icon: LayoutDashboard },
  { value: 'dispositivos', label: 'Dispositivos', icon: Network },
  { value: 'analitica', label: 'Analítica', icon: BarChart3 },
  { value: 'integraciones', label: 'Integraciones', icon: Plug },
  { value: 'sistema', label: 'Sistema', icon: Activity },
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
  // Bumped when a scan finishes so the mounted panels re-poll.
  const [refreshKey, setRefreshKey] = useState(0)
  const bump = useCallback(() => setRefreshKey((k) => k + 1), [])

  // Remember the last section across reloads (per-viewer convenience).
  const [tab, setTab] = useState(() => {
    try {
      return localStorage.getItem('netscan_tab') || 'resumen'
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
      {/* Fixed, heavily-blurred gradient blobs behind everything — the "aurora."
          Each drifts on its own slow, offset loop (different keyframe +
          duration + delay) so the four never move in sync. */}
      <div
        className="aurora-blob -left-32 -top-56 h-[620px] w-[620px] opacity-40"
        style={{
          background: 'radial-gradient(circle at 30% 30%, var(--violet), transparent 70%)',
          animation: 'aurora-drift-1 52s ease-in-out infinite',
        }}
      />
      <div
        className="aurora-blob -right-64 top-48 h-[700px] w-[700px] opacity-30"
        style={{
          background: 'radial-gradient(circle at 60% 40%, var(--teal), transparent 70%)',
          animation: 'aurora-drift-2 64s ease-in-out infinite',
          animationDelay: '-12s',
        }}
      />
      <div
        className="aurora-blob -bottom-64 left-1/3 h-[560px] w-[560px] opacity-25"
        style={{
          background: 'radial-gradient(circle at 50% 50%, var(--pink), transparent 70%)',
          animation: 'aurora-drift-3 58s ease-in-out infinite',
          animationDelay: '-30s',
        }}
      />
      <div
        className="aurora-blob bottom-24 right-[10%] h-[480px] w-[480px] opacity-20"
        style={{
          background: 'radial-gradient(circle, var(--blue), transparent 70%)',
          animation: 'aurora-drift-4 70s ease-in-out infinite',
          animationDelay: '-45s',
        }}
      />

      <div className="relative z-10 mx-auto max-w-[1560px] px-4 pb-14 pt-5 sm:px-6">
        <HeroTitle />
        <Header onScanDone={bump} />

        <Tabs value={tab} onValueChange={onTab} className="mt-5 gap-4">
          <TabsList className="glass grid h-auto w-full grid-cols-5 gap-1 rounded-xl bg-white/[0.055] p-1.5">
            {TABS.map(({ value, label, icon: Icon }) => (
              <TabsTrigger
                key={value}
                value={value}
                className="gap-1.5 rounded-lg px-2 py-2 text-xs font-semibold text-muted-foreground transition-colors data-[state=active]:bg-white/10 data-[state=active]:text-foreground data-[state=active]:shadow-sm sm:text-sm"
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="hidden sm:inline">{label}</span>
              </TabsTrigger>
            ))}
          </TabsList>

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
