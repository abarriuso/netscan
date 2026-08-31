import { useCallback, useState } from 'react'
import TokenDialog from '@/components/TokenDialog'
import HeroTitle from '@/components/HeroTitle'
import Header from '@/sections/Header'
import StatCards from '@/sections/StatCards'
import DevicesTable from '@/sections/DevicesTable'
import Integrations from '@/sections/Integrations'
import AlertsFeed from '@/sections/AlertsFeed'
import CapabilitiesBar from '@/sections/CapabilitiesBar'
import AnalyticsPanel from '@/sections/AnalyticsPanel'
import ServicesPanel from '@/sections/ServicesPanel'
import SystemStatus from '@/sections/SystemStatus'
import LogConsole from '@/sections/LogConsole'

export default function Home() {
  // Bumped when a scan finishes so every panel re-polls
  const [refreshKey, setRefreshKey] = useState(0)
  const bump = useCallback(() => setRefreshKey((k) => k + 1), [])

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-background text-foreground">
      <TokenDialog />
      {/* Fixed, heavily-blurred gradient blobs behind everything — the "aurora."
          Each drifts on its own slow, offset loop (different keyframe +
          duration + delay) so the four never move in sync — a shared cycle
          would read as one mechanical pulse instead of ambient motion. */}
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

      <div className="relative z-10 mx-auto max-w-[1560px] px-6 pb-14 pt-5">
        <HeroTitle />
        <Header onScanDone={bump} />
        <main className="animate-in fade-in mt-5 space-y-[18px] duration-500">
          <StatCards refreshKey={refreshKey} />
          <SystemStatus />
          <div className="grid gap-[18px] xl:grid-cols-[1.35fr_1fr]">
            <DevicesTable refreshKey={refreshKey} />
            <AlertsFeed refreshKey={refreshKey} />
          </div>
          <div className="grid gap-[18px] lg:grid-cols-2">
            <CapabilitiesBar />
            <LogConsole />
          </div>
          <AnalyticsPanel refreshKey={refreshKey} />
          <ServicesPanel refreshKey={refreshKey} />
          <Integrations />
        </main>
      </div>
    </div>
  )
}
