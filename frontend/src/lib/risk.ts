import type { RiskLevel } from '@/types'

/** Colour classes per risk level (badge, bar, text). */
export const LEVEL_STYLE: Record<RiskLevel | 'info', { text: string; bar: string; badge: string }> = {
  low: { text: 'text-ok', bar: 'bg-ok', badge: 'border-ok/40 bg-ok/[0.12] text-ok' },
  medium: { text: 'text-warn', bar: 'bg-warn', badge: 'border-warn/50 bg-warn/[0.12] text-warn' },
  high: { text: 'text-[#ff8a5c]', bar: 'bg-[#ff8a5c]', badge: 'border-[#ff8a5c]/50 bg-[#ff8a5c]/[0.12] text-[#ff8a5c]' },
  critical: { text: 'text-destructive', bar: 'bg-destructive', badge: 'border-destructive/60 bg-destructive/[0.14] text-destructive' },
  info: { text: 'text-muted-foreground', bar: 'bg-muted-foreground', badge: 'border-border text-muted-foreground' },
}
