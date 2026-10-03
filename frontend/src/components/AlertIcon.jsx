import { Eye, OctagonAlert, ShieldAlert, VideoOff } from 'lucide-react'

const ICONS = { ShieldAlert, OctagonAlert, Eye, VideoOff }

export default function AlertIcon({ name, className = 'h-4 w-4' }) {
  const Icon = ICONS[name] ?? ShieldAlert
  return <Icon className={className} />
}
