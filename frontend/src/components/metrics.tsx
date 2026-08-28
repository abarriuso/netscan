// Reusable animated metric primitives — count-up numbers, smooth meters,
// quality badges and mini sparkbars. Kept dependency-free (CSS transitions +
// requestAnimationFrame) so nothing janks on frequent polling.
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

/** Colour ramp: ok (good/low) → warn → destructive (bad/high) — the three
 *  semantic status tokens, never a decorative rainbow. */
function ramp(pct: number, invert = false): string {
  const p = invert ? 100 - pct : pct
  if (p < 60) return 'bg-ok'
  if (p < 80) return 'bg-warn'
  return 'bg-destructive'
}

export function Meter({
  percent,
  label,
  value,
  invertColor = false,
  className,
}: {
  percent: number
  label?: string
  value?: string
  invertColor?: boolean
  className?: string
}) {
  const clamped = Math.max(0, Math.min(100, percent || 0))
  const animated = useAnimatedNumber(clamped)
  return (
    <div className={cn('space-y-1', className)}>
      {(label || value) && (
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span className="truncate">{label}</span>
          <span className="font-mono tabular-nums text-foreground">{value}</span>
        </div>
      )}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn('h-full rounded-full transition-[width] duration-500 ease-out', ramp(clamped, invertColor))}
          style={{ width: `${animated}%` }}
        />
      </div>
    </div>
  )
}

export function QualityBadge({ score }: { score: number | null | undefined }) {
  if (score == null) return <span className="text-xs text-muted-foreground">—</span>
  const color = score >= 80 ? 'text-ok' : score >= 50 ? 'text-warn' : 'text-destructive'
  const dot = score >= 80 ? 'bg-ok' : score >= 50 ? 'bg-warn' : 'bg-destructive'
  return (
    <span className={cn('inline-flex items-center gap-1 font-mono text-xs', color)}>
      <span className={cn('h-1.5 w-1.5 rounded-full', dot)} />
      {score}
    </span>
  )
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
    <div className={cn('flex h-8 items-end gap-[2px]', className)}>
      {values.map((v, i) => {
        const h = v == null ? 0 : Math.max(6, (v / max) * 100)
        const pct = v == null ? 0 : (v / max) * 100
        return (
          <div
            key={i}
            className={cn(
              'w-full rounded-sm transition-all duration-300',
              v == null ? 'bg-muted' : ramp(pct, invertColor),
            )}
            style={{ height: `${h}%` }}
          />
        )
      })}
    </div>
  )
}
