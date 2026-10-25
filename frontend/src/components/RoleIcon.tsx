import { HelpCircle } from 'lucide-react'
import { ROLE_COLOR, ROLE_ICON } from '@/lib/roles'
import type { DeviceRole } from '@/types'

export function RoleIcon({ role, className = 'h-3.5 w-3.5' }: { role: DeviceRole; className?: string }) {
  const Icon = ROLE_ICON[role] ?? HelpCircle
  return <Icon className={className} style={{ color: ROLE_COLOR[role] }} strokeWidth={1.8} aria-hidden />
}
