import { useI18n } from '@/i18n/context'

/** The "NETSCAN" wordmark that opens the dashboard. A wide display face
 *  (Unbounded) revealed left→right by a scanner beam, then the beam re-sweeps
 *  every few seconds and the "SCAN" gradient drifts. Purely decorative and
 *  aria-hidden: the accessible heading lives in Header.tsx. All motion is
 *  CSS (index.css, `.hero-*`) and is killed under prefers-reduced-motion. */
export default function HeroTitle() {
  const { t } = useI18n()
  return (
    <div className="pointer-events-none mb-3 select-none pb-4 pt-6 text-center" aria-hidden="true">
      <div className="relative inline-block">
        <div className="hero-word">
          <span className="text-foreground">NET</span>
          <span className="hero-scan">SCAN</span>
        </div>
        <div className="hero-beam-track">
          <span className="hero-beam" />
        </div>
      </div>
      <div className="hero-tagline">{t('heroTagline')}</div>
    </div>
  )
}
