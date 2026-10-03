import { useState } from 'react'
import { Download, Eye, Film, OctagonAlert, Play, ShieldAlert, Trash2, User } from 'lucide-react'
import { downloadUrl, thumbnailUrl } from '../api'
import { formatBytes, formatDateTime, formatDuration, percent, timeAgo } from '../utils/format'
import { Badge } from './ui'
import { PeopleSummary } from './EventBadges'

const BADGES = {
  restricted_area: { label: 'RESTRICTED AREA', cls: 'bg-red-600 text-white', icon: OctagonAlert },
  unknown_person: { label: 'UNKNOWN PERSON', cls: 'bg-red-600 text-white', icon: ShieldAlert },
  suspicious_activity: { label: 'SUSPICIOUS', cls: 'bg-amber-500 text-black', icon: Eye },
  person: { label: 'PERSON', cls: 'bg-sky-600/90 text-white', icon: User },
}

export default function RecordingCard({ event, cameraName, onPlay, onDelete }) {
  const [thumbFailed, setThumbFailed] = useState(false)

  return (
    <div className="group overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60">
      <button
        onClick={() => onPlay(event)}
        className="relative block aspect-video w-full bg-slate-950 text-left"
        aria-label={`Play recording from ${cameraName}`}
      >
        {event.playable && !thumbFailed ? (
          <img
            src={thumbnailUrl(event.id)}
            alt=""
            loading="lazy"
            onError={() => setThumbFailed(true)}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-slate-700">
            <Film className="h-10 w-10" />
          </div>
        )}
        <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition group-hover:bg-black/40 group-hover:opacity-100">
          <span className="rounded-full bg-sky-600 p-3 text-white">
            <Play className="h-5 w-5 fill-current" />
          </span>
        </span>
        <span className="absolute bottom-2 right-2 rounded bg-black/75 px-1.5 py-0.5 font-mono text-xs text-slate-200">
          {formatDuration(event)}
        </span>
        {BADGES[event.event_type] && (
          <span className={`absolute left-2 top-2 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-bold ${BADGES[event.event_type].cls}`}>
            {(() => {
              const Icon = BADGES[event.event_type].icon
              return <Icon className="h-3 w-3" />
            })()}
            {BADGES[event.event_type].label}
            {event.event_type === 'person' && ` ${percent(event.max_confidence)}`}
          </span>
        )}
      </button>

      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm font-medium">{cameraName}</p>
          <Badge>{formatBytes(event.size_bytes)}</Badge>
        </div>
        <p className="text-xs text-slate-400" title={formatDateTime(event.timestamp)}>
          {formatDateTime(event.timestamp)} · {timeAgo(event.timestamp)}
        </p>
        {(event.people?.length > 0 || event.unknown_faces > 0) && <PeopleSummary event={event} />}
        {(onDelete || event.playable) && (
          <div className="flex justify-end gap-1 pt-1">
            {event.playable && (
              <a
                href={downloadUrl(event.id)}
                download
                aria-label="Download recording"
                className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
              >
                <Download className="h-4 w-4" />
              </a>
            )}
            {onDelete && (
              <button
                onClick={() => onDelete(event)}
                aria-label="Delete recording"
                className="rounded p-1.5 text-slate-400 hover:bg-red-500/10 hover:text-red-400"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
