import { useId } from 'react'

/** The NetScan mark: an "N" drawn as a network path — four hosts (nodes)
 *  joined by links, cyan on the left, magenta on the right. Same geometry as
 *  the favicon in index.html (keep the two in sync). With `animated`, a ping
 *  ring pulses out of the top-right host. */
export default function Logo({ size = 40, animated = false }: { size?: number; animated?: boolean }) {
  // Unique gradient id per instance: two logos on a page must not share defs.
  const grad = `ns-logo-${useId().replace(/:/g, '')}`
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="NetScan" className="shrink-0">
      <defs>
        <linearGradient id={grad} x1="9" y1="9" x2="23" y2="23" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#2de2e6" />
          <stop offset="1" stopColor="#ff2fb9" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="4" fill="#0b0d12" stroke="#2de2e6" strokeOpacity="0.4" />
      <path
        d="M9.5 22.5V9.5L22.5 22.5V9.5"
        fill="none"
        stroke={`url(#${grad})`}
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {animated && <circle className="logo-ping" cx="22.5" cy="9.5" r="2.5" fill="none" stroke="#ff2fb9" strokeWidth="1.2" />}
      <circle cx="9.5" cy="22.5" r="2.5" fill="#2de2e6" />
      <circle cx="9.5" cy="9.5" r="2.5" fill="#2de2e6" />
      <circle cx="22.5" cy="22.5" r="2.5" fill="#ff2fb9" />
      <circle cx="22.5" cy="9.5" r="2.5" fill="#ff2fb9" />
    </svg>
  )
}
