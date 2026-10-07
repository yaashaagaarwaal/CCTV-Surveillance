import { Link } from 'react-router-dom'
import { Activity, ChevronRight, Eye, OctagonAlert, Play, ShieldAlert, User } from 'lucide-react'
import { formatDateTime, percent, timeAgo } from '../utils/format'
import { Card } from './ui'
import { EventStatusBadge } from './EventBadges'

function eventTitle(event) {
  if (event.event_type === 'restricted_area') return 'Person in restricted area'
  if (event.event_type === 'unknown_person') return 'Unknown person'
  if (event.event_type === 'suspicious_activity') return 'Suspicious activity'
  if (event.event_type === 'person') return event.people?.length ? `${event.people.join(', ')} recognized` : 'Person detected'
  return 'Motion detected'
}

const STYLE = {
  restricted_area: ['bg-red-500/15 text-red-400', OctagonAlert],
  unknown_person: ['bg-red-500/15 text-red-400', ShieldAlert],
  suspicious_activity: ['bg-amber-500/15 text-amber-400', Eye],
  person: ['bg-sky-500/15 text-sky-400', User],
  motion: ['bg-slate-800 text-slate-400', Activity],
}

export default function RecentEvents({ events, nameOf, onSelect }) {
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Activity className="h-4 w-4 text-slate-400" />
          Recent events
        </h2>
        <Link to="/events" className="flex items-center text-xs text-sky-400 hover:underline">
          View all <ChevronRight className="h-3 w-3" />
        </Link>
      </div>

      {events.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-500">No events yet — they appear when motion is detected.</p>
      ) : (
        <ul className="divide-y divide-slate-800">
          {events.map((event) => (
            <li key={event.id}>
              <button
                onClick={() => onSelect(event)}
                className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-slate-800/40"
              >
                {(() => {
                  const [cls, Icon] = STYLE[event.event_type] ?? STYLE.motion
                  return (
                    <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${cls}`}>
                      <Icon className="h-4 w-4" />
                    </span>
                  )
                })()}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {eventTitle(event)}
                    <span className="font-normal text-slate-400"> · {nameOf(event.camera_id)}</span>
                  </span>
                  {event.reasons?.length > 0 && <span className="block truncate text-xs text-amber-300/90">{event.reasons[event.reasons.length - 1].message}</span>}
                  <span className="block text-xs text-slate-500" title={formatDateTime(event.timestamp)}>
                    {formatDateTime(event.timestamp)} · {timeAgo(event.timestamp)}
                    {event.max_confidence != null && ` · ${percent(event.max_confidence)}`}
                  </span>
                </span>
                <EventStatusBadge status={event.status} />
                {event.playable && <Play className="hidden h-4 w-4 text-slate-500 sm:block" />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
