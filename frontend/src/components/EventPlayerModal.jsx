import { useState } from 'react'

function EventPlayerModal({ event, onClose }) {
  const [videoError, setVideoError] = useState(false)

  if (!event) return null

  const videoUrl = `/api/events/${event.id}/video`

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-lg border border-slate-800 bg-slate-900 p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-medium">
            Event #{event.id} — {event.camera_id}
          </h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-100"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        {!event.has_recording ? (
          <p className="text-sm text-slate-500">This event has no recording.</p>
        ) : videoError ? (
          <p className="text-sm text-red-400">
            Could not load this recording — the file may be missing or corrupted.
          </p>
        ) : (
          <video
            key={videoUrl}
            src={videoUrl}
            controls
            autoPlay
            className="w-full rounded bg-black"
            onError={() => setVideoError(true)}
          />
        )}

        {event.has_recording && !videoError && (
          <a
            href={videoUrl}
            download
            className="mt-3 inline-block text-sm text-blue-400 hover:underline"
          >
            Download recording
          </a>
        )}
      </div>
    </div>
  )
}

export default EventPlayerModal
