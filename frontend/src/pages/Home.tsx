import { useCallback, useState } from 'react'
import Header from '@/sections/Header'
import StatCards from '@/sections/StatCards'
import DevicesTable from '@/sections/DevicesTable'
import Integrations from '@/sections/Integrations'
import AlertsFeed from '@/sections/AlertsFeed'
import CapabilitiesBar from '@/sections/CapabilitiesBar'
import AnalyticsPanel from '@/sections/AnalyticsPanel'
import ServicesPanel from '@/sections/ServicesPanel'

export default function Home() {
  // Bumped when a scan finishes so every panel re-polls
  const [refreshKey, setRefreshKey] = useState(0)
  const bump = useCallback(() => setRefreshKey((k) => k + 1), [])

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Header onScanDone={bump} />
      <main className="space-y-3 p-6">
        <StatCards refreshKey={refreshKey} />
        <div className="grid gap-3 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <DevicesTable refreshKey={refreshKey} />
          </div>
          <div className="space-y-3">
            <AlertsFeed refreshKey={refreshKey} />
            <CapabilitiesBar />
          </div>
        </div>
        <AnalyticsPanel refreshKey={refreshKey} />
        <ServicesPanel refreshKey={refreshKey} />
        <Integrations />
      </main>
    </div>
  )
}
