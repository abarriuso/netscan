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

/** Global token entry dialog. Opens itself either when the API rejects a
 *  request with 401 (`onAuthRequired`) or when the user clicks the header's
 *  settings button (`onTokenDialogRequested`) to change a saved token. */
export default function TokenDialog() {
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
      <DialogContent className="glass border-white/[0.12] bg-[#141021]/90 text-foreground shadow-2xl backdrop-blur-xl backdrop-saturate-150 sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <div
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
              style={{ background: 'linear-gradient(135deg, var(--violet), var(--blue))' }}
            >
              <KeyRound className="h-4 w-4 text-white" />
            </div>
            <DialogTitle>Token de API</DialogTitle>
          </div>
          <DialogDescription>
            {required
              ? 'Este NetScan requiere un token para hablar con la API.'
              : 'Cambia el token guardado en este navegador.'}{' '}
            Está en <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[11px]">/etc/netscan/netscan.env</code>{' '}
            dentro del servidor (variable <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[11px]">NETSCAN_API_TOKEN</code>).
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
            placeholder={hasToken() ? '••••••••••••••••' : 'pega el token aquí'}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && save()}
            className="border-white/[0.12] bg-white/[0.04] font-mono text-sm"
          />
        </div>

        <DialogFooter>
          <button
            onClick={dismiss}
            className="rounded-[10px] px-4 py-2 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            {required ? 'Ahora no' : 'Cancelar'}
          </button>
          <button
            onClick={save}
            disabled={!value.trim()}
            className="rounded-[10px] px-4 py-2 text-[13px] font-semibold text-white shadow-[0_4px_20px_rgba(109,40,217,0.45)] transition-[filter,transform] duration-150 hover:brightness-110 active:scale-[0.98] disabled:opacity-50 disabled:hover:brightness-100"
            style={{ background: 'linear-gradient(135deg, var(--violet), var(--blue))' }}
          >
            Guardar
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
