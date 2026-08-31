// Big ASCII wordmark for the dashboard's hero moment — generated with
// pyfiglet's "doom" font (the same font id-Software's tools used for their
// own text-mode banners; verified 46-char-wide on every line via a script,
// not hand-typed, so the letterforms can't drift out of alignment).
const DOOM_ASCII =
  " _   _  _____ _____ _____ _____   ___   _   _ \n| \\ | ||  ___|_   _/  ___/  __ \\ / _ \\ | \\ | |\n|  \\| || |__   | | \\ `--.| /  \\// /_\\ \\|  \\| |\n| . ` ||  __|  | |  `--. \\ |    |  _  || . ` |\n| |\\  || |___  | | /\\__/ / \\__/\\| | | || |\\  |\n\\_| \\_/\\____/  \\_/ \\____/ \\____/\\_| |_/\\_| \\_/"

/** The big DOOM-font ASCII "NETSCAN" wordmark that opens the dashboard —
 *  translucent over the aurora blobs (no glass card behind it, the blobs
 *  bleed straight through the letterforms), gradient-filled, with a slow
 *  compositor-only sheen sweep. Purely decorative: aria-hidden, the real
 *  accessible heading lives in Header.tsx's "NetScan" text. */
export default function HeroTitle() {
  return (
    <div className="pointer-events-none select-none overflow-x-auto pb-1 pt-2 text-center" aria-hidden="true">
      <pre
        className="hero-ascii mx-auto inline-block whitespace-pre font-mono text-[9px] font-bold leading-[1.15] sm:text-[13px] md:text-[17px] lg:text-[21px]"
      >
        {DOOM_ASCII}
      </pre>
    </div>
  )
}
