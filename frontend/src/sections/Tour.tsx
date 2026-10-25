import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Play, Trophy, X } from 'lucide-react'
import { endTour } from '@/lib/tour'
import { useI18n, type TextKey } from '@/i18n/context'

interface Step {
  id: string
  title: TextKey
  body: TextKey
  /** CSS selector of the element to spotlight; none = centred dialogue. */
  target?: string
  /** Tab to open before showing the step, so its content is visible. */
  tab?: string
}

// The order follows how a first-time user meets the app: start a scan, read
// the header, then walk the tabs left to right, end on the terminal.
const STEPS: Step[] = [
  { id: 'welcome', title: 'tour_welcome_title', body: 'tour_welcome_body' },
  { id: 'scan', title: 'tour_scan_title', body: 'tour_scan_body', target: '[data-tour="scan"]' },
  { id: 'mode', title: 'tour_mode_title', body: 'tour_mode_body', target: '[data-tour="mode"]' },
  { id: 'tabs', title: 'tour_tabs_title', body: 'tour_tabs_body', target: '[data-tour="tabs"]' },
  { id: 'live', title: 'tour_live_title', body: 'tour_live_body', target: '[data-tour="tab-live"]', tab: 'live' },
  { id: 'overview', title: 'tour_overview_title', body: 'tour_overview_body', target: '[data-tour="tab-resumen"]', tab: 'resumen' },
  { id: 'devices', title: 'tour_devices_title', body: 'tour_devices_body', target: '[data-tour="tab-dispositivos"]', tab: 'dispositivos' },
  { id: 'map', title: 'tour_map_title', body: 'tour_map_body', target: '[data-tour="tab-mapa"]', tab: 'mapa' },
  { id: 'security', title: 'tour_security_title', body: 'tour_security_body', target: '[data-tour="tab-seguridad"]', tab: 'seguridad' },
  { id: 'analytics', title: 'tour_analytics_title', body: 'tour_analytics_body', target: '[data-tour="tab-analitica"]', tab: 'analitica' },
  { id: 'tools', title: 'tour_tools_title', body: 'tour_tools_body', target: '[data-tour="tab-herramientas"]', tab: 'herramientas' },
  { id: 'integrations', title: 'tour_integrations_title', body: 'tour_integrations_body', target: '[data-tour="tab-integraciones"]', tab: 'integraciones' },
  { id: 'system', title: 'tour_system_title', body: 'tour_system_body', target: '[data-tour="tab-sistema"]', tab: 'sistema' },
  { id: 'terminal', title: 'tour_terminal_title', body: 'tour_terminal_body', target: '[data-tour="terminal"]' },
  { id: 'done', title: 'tour_done_title', body: 'tour_done_body' },
]

const PAD = 6 // spotlight margin around the target, px
const GAP = 14 // space between spotlight and dialogue, px
const CARD_W = 400

interface Box {
  top: number
  left: number
  width: number
  height: number
}

function reducedMotion(): boolean {
  return typeof window === 'undefined' || !window.matchMedia || window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Game-style text reveal; skipped under reduced motion. `done` = fully shown.
 *  The revealed count is stored together with its text, so a new step starts
 *  from zero without resetting state inside an effect (no one-frame flash of
 *  the previous line). */
function useTypewriter(text: string, cps = 90): { shown: string; done: boolean; finish: () => void } {
  const [state, setState] = useState(() => ({ text, count: reducedMotion() ? text.length : 0 }))
  const count = state.text === text ? state.count : reducedMotion() ? text.length : 0
  useEffect(() => {
    if (reducedMotion()) return
    const start = performance.now()
    const id = setInterval(() => {
      const n = Math.min(text.length, Math.floor(((performance.now() - start) / 1000) * cps))
      setState((s) => (s.text === text && s.count >= n ? s : { text, count: n }))
      if (n >= text.length) clearInterval(id)
    }, 16)
    return () => clearInterval(id)
  }, [text, cps])
  return {
    shown: text.slice(0, count),
    done: count >= text.length,
    finish: () => setState({ text, count: text.length }),
  }
}

function sameBox(a: Box | null, b: Box | null): boolean {
  return a === b || (!!a && !!b && a.top === b.top && a.left === b.left && a.width === b.width && a.height === b.height)
}

/** Track the viewport box of the step's target (tabs load lazily and the
 *  layout shifts, so it is re-measured continuously while the tour is open).
 *  The box is stored with its selector: a previous step's box is never shown. */
function useTargetBox(selector: string | undefined): Box | null {
  const [state, setState] = useState<{ selector: string; box: Box | null } | null>(null)
  useLayoutEffect(() => {
    if (!selector) return
    let scrolled = false
    const measure = () => {
      const el = document.querySelector(selector)
      let next: Box | null = null
      // A target hidden at this viewport size (display:none) measures 0×0:
      // fall back to a centred dialogue instead of a spotlight at the corner.
      const visible = el && el.getClientRects().length > 0
      if (el && visible) {
        if (!scrolled) {
          scrolled = true
          el.scrollIntoView({ block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth' })
        }
        const r = el.getBoundingClientRect()
        next = { top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 }
      }
      setState((prev) => (prev && prev.selector === selector && sameBox(prev.box, next) ? prev : { selector, box: next }))
    }
    const raf = requestAnimationFrame(measure)
    const id = setInterval(measure, 120)
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => {
      cancelAnimationFrame(raf)
      clearInterval(id)
      window.removeEventListener('resize', measure)
      window.removeEventListener('scroll', measure, true)
    }
  }, [selector])
  return selector && state?.selector === selector ? state.box : null
}

/** First-run walkthrough, video-game tutorial style: the rest of the screen
 *  dims, the element being explained is spotlighted, and a dialogue box
 *  types out what it does. Arrow keys / Enter advance, Esc skips. */
export default function Tour({
  onNavigate,
  onStartScan,
}: {
  onNavigate: (tab: string) => void
  onStartScan?: () => void
}) {
  const { t } = useI18n()
  const [index, setIndex] = useState(0)
  const step = STEPS[index]
  const box = useTargetBox(step.target)
  const text = useTypewriter(t(step.body))
  const cardRef = useRef<HTMLDivElement>(null)
  const last = index === STEPS.length - 1

  useEffect(() => {
    if (step.tab) onNavigate(step.tab)
  }, [step.tab, onNavigate])

  useEffect(() => {
    cardRef.current?.focus()
  }, [index])

  const next = useCallback(() => {
    if (!text.done) {
      text.finish() // first press completes the line, like in games
      return
    }
    if (last) endTour('done')
    else setIndex((i) => i + 1)
  }, [text, last])
  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), [])
  const skip = useCallback(() => endTour('skipped', index), [index])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        skip()
      } else if (e.key === 'ArrowRight' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        e.stopPropagation()
        next()
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        back()
      }
    }
    // Capture phase: the tour's keys must not also trigger the R/F scan
    // shortcuts or the terminal toggle underneath.
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [next, back, skip])

  // Dialogue placement: below the spotlight if it fits, otherwise above it;
  // centred when the step has no target (or it is not on screen yet).
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1280
  const vh = typeof window !== 'undefined' ? window.innerHeight : 800
  const width = Math.min(CARD_W, vw - 32)
  let cardStyle: React.CSSProperties
  if (box) {
    const left = Math.min(Math.max(box.left, 16), vw - width - 16)
    const below = box.top + box.height + GAP
    cardStyle =
      vh - below > 260 || box.top < 260
        ? { top: Math.min(below, vh - 120), left, width }
        : { bottom: vh - box.top + GAP, left, width }
  } else {
    cardStyle = { top: '50%', left: '50%', width: Math.min(460, vw - 32), transform: 'translate(-50%, -50%)' }
  }

  const center = !box

  return (
    <div className="fixed inset-0 z-[45]" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      {/* Distinct keys: the spotlight must mount at its target, not morph
          out of the full-screen backdrop (it would sweep in from the corner). */}
      {box ? (
        <div
          key="spotlight"
          aria-hidden
          className="pointer-events-none absolute border-2 border-primary transition-all duration-300 ease-out motion-reduce:transition-none"
          style={{
            top: box.top,
            left: box.left,
            width: box.width,
            height: box.height,
            boxShadow: '0 0 0 9999px rgba(4, 6, 9, 0.66), 0 0 24px 4px rgba(45, 226, 230, 0.45)',
          }}
        >
          <span className="absolute -inset-[5px] animate-pulse border border-primary/40 motion-reduce:animate-none" />
        </div>
      ) : (
        <div key="backdrop" aria-hidden className="absolute inset-0 bg-[rgba(4,6,9,0.78)]" />
      )}

      <div
        ref={cardRef}
        tabIndex={-1}
        style={cardStyle}
        onClick={next}
        className="absolute cursor-pointer border-2 border-primary/70 bg-[rgb(9_11_15/0.98)] p-4 font-mono shadow-[6px_6px_0_0_rgba(45,226,230,0.25)] outline-none"
      >
        {/* header: mission counter + segmented progress, like a quest log */}
        <div className="mb-2 flex items-center justify-between gap-3 text-[10px] font-bold uppercase tracking-[0.18em] text-primary">
          <span>
            {t('tourLabel')} · {t('tourMission', index + 1, STEPS.length)}
          </span>
          <button
            onClick={(e) => {
              e.stopPropagation()
              skip()
            }}
            aria-label={t('tourSkip')}
            title={`${t('tourSkip')} (Esc)`}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="mb-3 flex gap-[3px]" aria-hidden>
          {STEPS.map((s, i) => (
            <span key={s.id} className={`h-1 flex-1 ${i < index ? 'bg-primary' : i === index ? 'bg-primary/60' : 'bg-white/[0.08]'}`} />
          ))}
        </div>

        <h2 id="tour-title" className="flex items-center gap-2 font-display text-[17px] font-extrabold tracking-tight text-foreground">
          {last && <Trophy className="h-4 w-4 text-[color:var(--accent-amber)]" />}
          {center && !last && (
            <span aria-hidden className="text-primary">
              ▸
            </span>
          )}
          {t(step.title)}
        </h2>
        <p className="mt-2 min-h-[4.5em] whitespace-pre-line text-[12.5px] leading-relaxed text-foreground/85">
          {text.shown}
          {!text.done && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-primary align-middle" />}
        </p>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[10px] text-muted-foreground">{t('tourKeys')}</span>
          <div className="flex items-center gap-2">
            {index > 0 && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  back()
                }}
                className="press flex items-center gap-1 border border-border px-2.5 py-1.5 text-[11px] uppercase tracking-wider text-muted-foreground hover:text-foreground"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                {t('tourBack')}
              </button>
            )}
            {last && onStartScan && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  endTour('done')
                  onStartScan()
                }}
                className="press flex items-center gap-1 border border-primary/60 px-2.5 py-1.5 text-[11px] font-bold uppercase tracking-wider text-primary hover:bg-primary/10"
              >
                <Play className="h-3.5 w-3.5" />
                {t('tourStartScan')}
              </button>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation()
                next()
              }}
              className="press flex items-center gap-1 bg-primary px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-primary-foreground"
            >
              {last ? t('tourFinish') : t('tourNext')}
              {!last && <ChevronRight className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
