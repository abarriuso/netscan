// Reusable animated metric primitives — count-up numbers, gradient meters,
// quality bars and mini sparkbars — plus the GlassPanel shell every section
// sits in. Kept dependency-free (CSS transitions + requestAnimationFrame) so
// nothing janks on frequent polling.
import { useAnimatedNumber } from '@/hooks/useNetscan'
import { cn } from '@/lib/utils'

export function AnimatedNumber({
  value,
  decimals = 0,
  suffix = '',
  prefix = '',
  className,
}: {
  value: number
  decimals?: number
  suffix?: string
  prefix?: string
  className?: string
}) {
  const animated = useAnimatedNumber(value)
  return (
    <span className={cn('tabular-nums', className)}>
      {prefix}
      {animated.toFixed(decimals)}
      {suffix}
    </span>
  )
}

/** Above these thresholds a meter switches from the decorative gradient to
 *  a flat semantic color — real danger stays legible, not just pretty. */
function fillClass(pct: number, invert = false): string | null {
  const p = invert ? 100 - pct : pct
  if (p >= 90) return 'bg-destructive'
  if (p >= 75) return 'bg-warn'
  return null
}

export function Meter({
  percent,
  label,
  value,
  invertColor = false,
  gradient = 'violet-teal',
  className,
}: {
  percent: number
  label?: string
  value?: string
  invertColor?: boolean
  /** Which two-stop gradient to use for the "normal range" fill. */
  gradient?: 'violet-teal' | 'blue-teal' | 'pink-violet'
  className?: string
}) {
  const clamped = Math.max(0, Math.min(100, percent || 0))
  const animated = useAnimatedNumber(clamped)
  const solid = fillClass(clamped, invertColor)
  const gradientClass =
    gradient === 'blue-teal'
      ? 'bg-[linear-gradient(90deg,var(--blue),var(--teal))]'
      : gradient === 'pink-violet'
        ? 'bg-[linear-gradient(90deg,#be185d,var(--pink))]'
        : 'bg-[linear-gradient(90deg,var(--violet-2),var(--violet))]'
  return (
    <div className={cn('space-y-1.5', className)}>
      {(label || value) && (
        <div className="flex items-center justify-between text-[11.5px] text-muted-foreground">
          <span className="truncate">{label}</span>
          <span className="font-mono tabular-nums text-foreground/90">{value}</span>
        </div>
      )}
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/[0.07]">
        <div
          className={cn('h-full rounded-full transition-[width] duration-500 ease-out', solid ?? gradientClass)}
          style={{ width: `${animated}%` }}
        />
      </div>
    </div>
  )
}

export function QualityBadge({ score }: { score: number | null | undefined }) {
  // Hooks can't be called conditionally, so this runs unconditionally even
  // when score is null (the early return below just never uses its result).
  const animated = useAnimatedNumber(score ?? 0)
  if (score == null) return <span className="text-xs text-muted-foreground">—</span>
  const gradient =
    score >= 80
      ? 'bg-[linear-gradient(90deg,var(--teal),#34d399)]'
      : score >= 50
        ? 'bg-[linear-gradient(90deg,#fbbf24,#fca311)]'
        : 'bg-[linear-gradient(90deg,#f87171,#ef4444)]'
  return (
    <span className="inline-flex items-center gap-2 font-mono text-xs">
      <span className="h-1.5 w-[46px] overflow-hidden rounded-full bg-white/[0.08]">
        <span
          className={cn('block h-full rounded-full transition-[width] duration-500 ease-out', gradient)}
          style={{ width: `${animated}%` }}
        />
      </span>
      {score}
    </span>
  )
}

/** Colour ramp for the plain (non-gradient) mini sparkbars. */
function ramp(pct: number, invert = false): string {
  const p = invert ? 100 - pct : pct
  if (p < 60) return 'bg-ok'
  if (p < 80) return 'bg-warn'
  return 'bg-destructive'
}

/** Tiny inline bar chart from a numeric series (nulls render as gaps). */
export function Sparkbar({
  values,
  className,
  invertColor = false,
}: {
  values: (number | null)[]
  className?: string
  invertColor?: boolean
}) {
  const nums = values.filter((v): v is number => v != null)
  const max = Math.max(1, ...nums)
  return (
    <div className={cn('flex h-8 items-end gap-[3px]', className)}>
      {values.map((v, i) => {
        const h = v == null ? 0 : Math.max(6, (v / max) * 100)
        const pct = v == null ? 0 : (v / max) * 100
        return (
          <div
            key={i}
            className={cn(
              'w-full rounded-sm transition-[height,background-color] duration-300 ease-out',
              v == null ? 'bg-white/[0.08]' : ramp(pct, invertColor),
            )}
            style={{ height: `${h}%` }}
          />
        )
      })}
    </div>
  )
}

/** The frosted-glass panel shell every section sits in — a title row
 *  (`h2` + optional right-aligned meta text) over the panel content. */
export function GlassPanel({
  title,
  meta,
  right,
  className,
  contentClassName,
  children,
}: {
  title: string
  /** Small muted text on the right of the title row, e.g. "12 discovered". */
  meta?: React.ReactNode
  /** Full replacement for the right side of the title row (overrides `meta`). */
  right?: React.ReactNode
  className?: string
  contentClassName?: string
  children: React.ReactNode
}) {
  return (
    <div className={cn('glass p-5', className)}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-[14.5px] font-bold tracking-tight">{title}</h2>
        {right ?? (meta && <span className="text-[11.5px] font-medium text-muted-foreground">{meta}</span>)}
      </div>
      <div className={contentClassName}>{children}</div>
    </div>
  )
}
