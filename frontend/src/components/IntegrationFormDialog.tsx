import { useEffect, useState } from 'react'
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
import { api } from '@/lib/api'
import type { IntegrationKind, IntegrationSetting } from '@/types'

interface FieldSpec {
  key: string
  label: string
  type?: 'text' | 'password' | 'number' | 'checkbox'
  placeholder?: string
  default?: string | number | boolean
}

const KIND_LABELS: Record<IntegrationKind, string> = {
  proxmox: 'Proxmox VE',
  truenas: 'TrueNAS',
  adguard: 'AdGuard Home',
  pihole: 'Pi-hole',
  custom: 'Personalizada (marcador)',
}

const KIND_FIELDS: Record<IntegrationKind, FieldSpec[]> = {
  proxmox: [
    { key: 'host', label: 'Host', placeholder: '192.168.1.10' },
    { key: 'port', label: 'Puerto', type: 'number', default: 8006 },
    { key: 'token_id', label: 'Token ID', placeholder: 'root@pam!netscan' },
    { key: 'token_secret', label: 'Token secreto', type: 'password' },
    { key: 'verify_ssl', label: 'Verificar certificado SSL', type: 'checkbox', default: false },
  ],
  truenas: [
    { key: 'host', label: 'Host', placeholder: '192.168.1.11' },
    { key: 'port', label: 'Puerto', type: 'number', default: 443 },
    { key: 'api_key', label: 'API key', type: 'password' },
    { key: 'use_ssl', label: 'Usar HTTPS', type: 'checkbox', default: true },
    { key: 'verify_ssl', label: 'Verificar certificado SSL', type: 'checkbox', default: false },
  ],
  adguard: [
    { key: 'host', label: 'Host', placeholder: '192.168.1.15' },
    { key: 'port', label: 'Puerto', type: 'number', default: 80 },
    { key: 'username', label: 'Usuario' },
    { key: 'password', label: 'Contraseña', type: 'password' },
    { key: 'use_ssl', label: 'Usar HTTPS', type: 'checkbox', default: false },
  ],
  pihole: [
    { key: 'host', label: 'Host', placeholder: '192.168.1.15' },
    { key: 'port', label: 'Puerto', type: 'number', default: 80 },
    { key: 'password', label: 'Contraseña de administrador', type: 'password' },
    { key: 'use_ssl', label: 'Usar HTTPS', type: 'checkbox', default: false },
  ],
  custom: [{ key: 'url', label: 'URL', placeholder: 'https://portainer.lan' }],
}

type FormValues = Record<string, string | number | boolean>

function defaultsFor(kind: IntegrationKind): FormValues {
  const values: FormValues = {}
  for (const f of KIND_FIELDS[kind]) values[f.key] = f.default ?? (f.type === 'checkbox' ? false : '')
  return values
}

export default function IntegrationFormDialog({
  open,
  onOpenChange,
  editing,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Pass an existing DB-backed integration to edit it; omit to create a new one. */
  editing?: IntegrationSetting | null
  onSaved: () => void
}) {
  const [kind, setKind] = useState<IntegrationKind>('custom')
  const [name, setName] = useState('')
  const [values, setValues] = useState<FormValues>(defaultsFor('custom'))
  const [logoFile, setLogoFile] = useState<File | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    if (editing) {
      setKind(editing.kind)
      setName(editing.name)
      setValues({ ...defaultsFor(editing.kind), ...editing.config })
    } else {
      setKind('custom')
      setName('')
      setValues(defaultsFor('custom'))
    }
    setLogoFile(null)
    setError(null)
  }, [open, editing])

  const changeKind = (next: IntegrationKind) => {
    setKind(next)
    setValues(defaultsFor(next))
  }

  const save = async () => {
    if (!name.trim()) {
      setError('Ponle un nombre.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      let id = editing?.id
      if (editing?.id) {
        await api.updateIntegration(editing.id, { name, config: values })
      } else {
        const created = await api.createIntegration(kind, name, values)
        id = created.id
      }
      if (kind === 'custom' && logoFile && id) {
        await api.uploadIntegrationLogo(id, logoFile)
      }
      onSaved()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar la integración.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass max-h-[85vh] overflow-y-auto border-border bg-popover text-foreground shadow-2xl sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{editing ? 'Editar integración' : 'Añadir integración'}</DialogTitle>
          <DialogDescription>
            {editing
              ? `${KIND_LABELS[editing.kind]} — cambia lo que haga falta.`
              : 'Conecta Proxmox, TrueNAS, AdGuard, Pi-hole, o añade un marcador propio con logo.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {!editing && (
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Tipo</Label>
              <div className="grid grid-cols-2 gap-1.5">
                {(Object.keys(KIND_LABELS) as IntegrationKind[]).map((k) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => changeKind(k)}
                    className={`rounded-none border px-3 py-2 text-left text-xs font-medium transition-colors ${
                      kind === k
                        ? 'border-primary/50 bg-primary/15 text-foreground'
                        : 'border-white/10 bg-white/[0.03] text-muted-foreground hover:border-white/20'
                    }`}
                  >
                    {KIND_LABELS[k]}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="integration-name" className="text-xs text-muted-foreground">
              Nombre
            </Label>
            <Input
              id="integration-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="ej. Proxmox principal"
              className="border-white/[0.12] bg-white/[0.04]"
            />
          </div>

          {KIND_FIELDS[kind].map((f) => (
            <div key={f.key} className="space-y-1.5">
              {f.type === 'checkbox' ? (
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={Boolean(values[f.key])}
                    onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.checked }))}
                    className="h-3.5 w-3.5 rounded border-white/20 bg-white/[0.04]"
                  />
                  {f.label}
                </label>
              ) : (
                <>
                  <Label className="text-xs text-muted-foreground">{f.label}</Label>
                  <Input
                    type={f.type ?? 'text'}
                    placeholder={f.placeholder}
                    value={String(values[f.key] ?? '')}
                    onChange={(e) =>
                      setValues((v) => ({
                        ...v,
                        [f.key]: f.type === 'number' ? Number(e.target.value) : e.target.value,
                      }))
                    }
                    className="border-white/[0.12] bg-white/[0.04] font-mono text-sm"
                  />
                </>
              )}
            </div>
          ))}

          {kind === 'custom' && (
            <div className="space-y-1.5">
              <Label className="text-xs text-muted-foreground">Logo (opcional — PNG/SVG/JPG/WEBP, máx. 2MB)</Label>
              <input
                type="file"
                accept="image/png,image/svg+xml,image/jpeg,image/webp"
                onChange={(e) => setLogoFile(e.target.files?.[0] ?? null)}
                className="block w-full text-xs text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-foreground"
              />
            </div>
          )}

          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <button
            onClick={() => onOpenChange(false)}
            className="rounded-none px-4 py-2 font-mono text-[12px] font-medium uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
          >
            Cancelar
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="rounded-none bg-primary px-4 py-2 font-mono text-[12px] font-bold uppercase tracking-wider text-primary-foreground shadow-hard-cyan transition-[filter,transform] duration-150 hover:brightness-110 disabled:opacity-50"
          >
            {saving ? 'Guardando…' : 'Guardar'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
