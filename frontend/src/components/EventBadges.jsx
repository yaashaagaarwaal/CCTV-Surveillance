import { Activity, Eye, OctagonAlert, ShieldAlert, User } from 'lucide-react'
import { EVENT_TYPES } from '../utils/meta'
import { Badge } from './ui'

const TYPE_ICONS = { motion: Activity, person: User, suspicious_activity: Eye, unknown_person: ShieldAlert, restricted_area: OctagonAlert }

export function EventTypeBadge({ type }) {
  const meta = EVENT_TYPES[type] ?? { label: type, tone: 'slate' }
  const Icon = TYPE_ICONS[type] ?? Activity
  return (
    <Badge tone={meta.tone}>
      <Icon className="h-3 w-3" />
      {meta.label}
    </Badge>
  )
}

const STATUS_TONES = {
  recording: ['amber', 'Recording'],
  completed: ['green', 'Completed'],
  failed: ['red', 'Failed'],
  interrupted: ['orange', 'Interrupted'],
}

export function EventStatusBadge({ status }) {
  const [tone, label] = STATUS_TONES[status] ?? ['slate', status]
  return (
    <Badge tone={tone}>
      {status === 'recording' && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-400" />}
      {label}
    </Badge>
  )
}

// Who was recognized in an event: known names, plus unknown / not-sure counts.
export function PeopleSummary({ event }) {
  const { people = [], unknown_faces: unknown = 0, uncertain_faces: unsure = 0 } = event
  if (!people.length && !unknown && !unsure) return <span className="text-slate-600">—</span>
  return (
    <span className="flex flex-wrap gap-1">
      {people.map((name) => (
        <Badge key={name} tone="green">
          {name}
        </Badge>
      ))}
      {unknown > 0 && <Badge tone="red">Unknown</Badge>}
      {unsure > 0 && <Badge tone="orange">Not sure</Badge>}
    </span>
  )
}
