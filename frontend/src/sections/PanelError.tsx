import { RotateCw } from 'lucide-react'
import { useI18n } from '@/i18n/context'

/** Inline error banner for dashboard panels — poll failures must be visible,
 *  and recoverable without waiting for the next poll cycle. Pass `onRetry` to
 *  render a retry button. */
export default function PanelError({
  error,
  onRetry,
}: {
  error: string | null
  onRetry?: () => void
}) {
  const { t } = useI18n()
  if (!error) return null
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 rounded-none border border-destructive/40 bg-destructive/10 px-3 py-2 font-mono text-[12px] text-destructive"
    >
      <span className="min-w-0 truncate">{t('noApi', error)}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex shrink-0 items-center gap-1.5 rounded-none border border-destructive/50 px-2 py-1 text-[11px] font-semibold uppercase tracking-wider transition-colors hover:bg-destructive/20"
        >
          <RotateCw className="h-3 w-3" />
          {t('retry')}
        </button>
      )}
    </div>
  )
}
