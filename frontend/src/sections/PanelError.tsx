/** Inline error banner for dashboard panels — poll failures must be visible. */
export default function PanelError({ error }: { error: string | null }) {
  if (!error) return null
  return (
    <p
      role="alert"
      className="rounded border border-red-500/40 bg-red-500/10 px-3 py-2 font-mono text-[11px] text-red-300"
    >
      sin conexión con la API — {error}
    </p>
  )
}
