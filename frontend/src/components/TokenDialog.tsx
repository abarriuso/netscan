import { useEffect, useState } from 'react'
import { KeyRound } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cancelAuth, hasToken, onAuthRequired, onTokenDialogRequested, submitToken } from '@/lib/api'
import { useI18n } from '@/i18n/context'

/** Global token entry dialog. Opens itself either when the API rejects a
 *  request with 401 (`onAuthRequired`) or when the user clicks the header's
 *  settings button (`onTokenDialogRequested`) to change a saved token. */
export default function TokenDialog() {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [required, setRequired] = useState(false)
  const [value, setValue] = useState('')

  useEffect(() => {
    const offRequired = onAuthRequired(() => {
      setRequired(true)
      setValue('')
      setOpen(true)
    })
    const offManual = onTokenDialogRequested(() => {
      setRequired(false)
      setValue('')
      setOpen(true)
    })
    return () => {
      offRequired()
      offManual()
    }
  }, [])

  const save = () => {
    if (!value.trim()) return
    submitToken(value.trim())
    setOpen(false)
  }

  const dismiss = () => {
    if (required) cancelAuth()
    setOpen(false)
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? setOpen(true) : dismiss())}>
      <DialogContent className="glass border-border bg-popover text-foreground shadow-2xl sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <div
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-none bg-primary"
            >
              <KeyRound className="h-4 w-4 text-primary-foreground" />
            </div>
            <DialogTitle>{t('apiToken')}</DialogTitle>
          </div>
          <DialogDescription>
            {required ? t('tokenRequired') : t('tokenChange')}{' '}
            {t('tokenWhereBefore')} <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[11px]">/etc/netscan/netscan.env</code>{' '}
            {t('tokenWhereInside')} <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[11px]">NETSCAN_API_TOKEN</code>).
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="netscan-token" className="text-xs text-muted-foreground">
            Token
          </Label>
          <Input
            id="netscan-token"
            type="password"
            autoFocus
            placeholder={hasToken() ? '••••••••••••••••' : t('tokenPlaceholder')}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && save()}
            className="border-white/[0.12] bg-white/[0.04] font-mono text-sm"
          />
        </div>

        <DialogFooter>
          <button
            onClick={dismiss}
            className="rounded-none px-4 py-2 font-mono text-[12px] font-medium uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
          >
            {required ? t('notNow') : t('cancel')}
          </button>
          <button
            onClick={save}
            disabled={!value.trim()}
            className="rounded-none bg-primary px-4 py-2 font-mono text-[12px] font-bold uppercase tracking-wider text-primary-foreground shadow-hard-cyan transition-[filter,transform] duration-150 hover:brightness-110 active:translate-x-0 disabled:opacity-50 disabled:hover:brightness-100"
          >
            {t('save')}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
