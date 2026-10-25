// Role → icon and colour (literal hexes: also used as SVG fills in the map).
import {
  Box,
  Camera,
  HardDrive,
  HelpCircle,
  Laptop,
  Lightbulb,
  Network,
  Printer,
  Radar,
  Router,
  Server,
  Smartphone,
  Tv,
  type LucideIcon,
} from 'lucide-react'
import type { DeviceRole } from '@/types'

export const ROLE_ICON: Record<DeviceRole, LucideIcon> = {
  gateway: Router,
  netscan: Radar,
  hypervisor: Server,
  nas: HardDrive,
  server: Server,
  workstation: Laptop,
  mobile: Smartphone,
  printer: Printer,
  media: Tv,
  camera: Camera,
  iot: Lightbulb,
  network: Network,
  vm: Box,
  unknown: HelpCircle,
}

export const ROLE_COLOR: Record<DeviceRole, string> = {
  gateway: '#2de2e6',
  netscan: '#ff2fb9',
  hypervisor: '#c4a7ff',
  nas: '#4cc9ff',
  server: '#36e09e',
  workstation: '#e9ecf1',
  mobile: '#ffbe37',
  printer: '#82909c',
  media: '#ff8a5c',
  camera: '#ff4a5e',
  iot: '#a3e635',
  network: '#2de2e6',
  vm: '#8b9cff',
  unknown: '#5b6573',
}
