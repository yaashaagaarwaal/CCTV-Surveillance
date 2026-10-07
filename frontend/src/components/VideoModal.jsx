import { useState } from 'react'
import { Download, VideoOff } from 'lucide-react'
import { downloadUrl, videoUrl } from '../api'
import { formatBytes, formatDateTime, formatDuration, percent } from '../utils/format'
import { EventReasons, EventTypeBadge, PeopleSummary } from './EventBadges'
import { Button, Modal } from './ui'

function Player({ event }) {
  const [failed, setFailed] = useState(false)
  if (!event.playable || failed) {
    return (
      <div className="flex aspect-video flex-col items-center justify-center gap-2 rounded-lg bg-slate-950 text-slate-500">
        <VideoOff className="h-8 w-8" />
        <p className="text-sm">
          {event.status === 'recording'
            ? 'This clip is still being recorded.'
            : 'This recording is unavailable — the file may be missing or corrupted.'}
        </p>
      </div>
    )
  }
  return (
    <video
      src={videoUrl(event.id)}
      controls
      autoPlay
      onError={() => setFailed(true)}
      className="aspect-video w-full rounded-lg bg-black"
    />
  )
}

export default function VideoModal({ event, cameraName, onClose }) {
  return (
    <Modal title={`${cameraName} — ${formatDateTime(event.timestamp)}`} onClose={onClose} wide>
      <div className="space-y-4">
        {/* keyed so a new event resets the player's error state */}
        <Player key={event.id} event={event} />
        {event.reasons?.length > 0 && (
          <div className="rounded-lg border border-slate-800 p-3">
            <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500">Why this was flagged</p>
            <EventReasons event={event} />
          </div>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-400">
            <EventTypeBadge type={event.event_type} />
            <PeopleSummary event={event} />
            {event.max_confidence != null && <span>Confidence {percent(event.max_confidence)}</span>}
            <span>· {formatDuration(event)}</span>
            <span>· {formatBytes(event.size_bytes)}</span>
          </div>
          {event.playable && (
            <a href={downloadUrl(event.id)} download>
              <Button variant="primary">
                <Download className="h-4 w-4" />
                Download
              </Button>
            </a>
          )}
        </div>
      </div>
    </Modal>
  )
}
