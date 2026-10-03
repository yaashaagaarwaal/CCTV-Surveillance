import { useEffect, useState } from 'react'
import { Maximize2, Minimize2, Moon, User, VideoOff } from 'lucide-react'
import { snapshotUrl, streamUrl } from '../api'
import { useNow } from '../hooks/useNow'
import { formatClock, percent } from '../utils/format'
import { Spinner } from './ui'

// Refreshing JPEG snapshots instead of holding a live MJPEG connection open.
// Browsers allow only ~6 simultaneous HTTP/1.1 connections per host, so
// beyond a few live streams the dashboard's own API calls would stall.
function SnapshotFeed({ cameraId, alt }) {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(id)
  }, [])
  return <img src={`${snapshotUrl(cameraId)}?t=${tick}`} alt={alt} className="h-full w-full object-contain" />
}

function OfflineView({ status, enabled }) {
  const connecting = status === 'connecting'
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-slate-950 text-slate-500">
      {connecting ? <Spinner className="h-8 w-8" /> : <VideoOff className="h-8 w-8" />}
      <p className="text-sm font-medium">{connecting ? 'Connecting…' : enabled ? 'Camera offline' : 'Camera disabled'}</p>
      {status === 'offline' && enabled && <p className="text-xs text-slate-600">Retrying automatically</p>}
    </div>
  )
}

/**
 * One camera in the dashboard grid, styled like an NVR channel: status and
 * REC indicators over the video, name and timestamp along the bottom.
 * `live` picks a real-time MJPEG stream vs. cheap refreshing snapshots.
 * "Expand" enlarges the very same tile (no second stream connection).
 */
export default function CameraTile({ camera, live }) {
  const [expanded, setExpanded] = useState(false)
  const now = useNow()
  const online = camera.status === 'online'
  const people = camera.people_detected ?? 0
  const alerting = online && people > 0
  const bestConfidence = alerting ? Math.max(...camera.detections.map((d) => d.confidence)) : null

  const lighting = online ? camera.lighting : null
  const nightLabel = lighting?.night ? (lighting.kind === 'infrared' ? 'NIGHT · IR' : 'NIGHT MODE') : null

  const faces = online ? (camera.faces ?? []) : []
  const knownNames = [...new Set(faces.filter((f) => f.label === 'known').map((f) => f.name))]
  const unknownCount = faces.filter((f) => f.label === 'unknown').length
  const unsureCount = faces.filter((f) => f.label === 'uncertain').length
  // Red = a stranger is in view; green = everyone in view is recognized.
  const ring = unknownCount > 0 ? 'red' : alerting && knownNames.length > 0 && unsureCount === 0 ? 'green' : alerting ? 'amber' : 'none'
  const RING_STYLES = {
    red: 'border-red-500/80 shadow-[0_0_0_1px_rgba(239,68,68,0.5)]',
    green: 'border-emerald-500/70 shadow-[0_0_0_1px_rgba(16,185,129,0.4)]',
    amber: 'border-amber-500/60',
    none: 'border-slate-800',
  }

  useEffect(() => {
    if (!expanded) return
    const onKey = (e) => e.key === 'Escape' && setExpanded(false)
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [expanded])

  return (
    <>
      {expanded && <div className="fixed inset-0 z-40 bg-black/85" onClick={() => setExpanded(false)} />}
      {expanded && <div className="aspect-video" />}

      <div
        className={`group overflow-hidden rounded-xl border bg-black transition-shadow ${RING_STYLES[ring]} ${expanded ? 'fixed inset-3 z-50 flex items-center sm:inset-10' : 'relative'}`}
      >
        <div className={`relative w-full bg-black ${expanded ? 'max-h-full aspect-video' : 'aspect-video'}`}>
          {online ? (
            live || expanded ? (
              <img src={streamUrl(camera.id)} alt={camera.name} className="h-full w-full object-contain" />
            ) : (
              <SnapshotFeed cameraId={camera.id} alt={camera.name} />
            )
          ) : (
            <OfflineView status={camera.status} enabled={camera.enabled} />
          )}

          <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 bg-gradient-to-b from-black/70 to-transparent p-2.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <span
                className={`inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[11px] font-bold tracking-wide ${
                  online ? 'bg-emerald-500/90 text-black' : 'bg-slate-700/90 text-slate-300'
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${online ? 'bg-black' : 'bg-slate-400'}`} />
                {online ? (live || expanded ? 'LIVE' : 'SNAPSHOT') : camera.status.toUpperCase()}
              </span>
              {nightLabel && (
                <span
                  title={
                    lighting.kind === 'infrared'
                      ? 'Infrared / night-vision feed detected. Detection runs on the raw and a contrast-enhanced copy; recordings are unenhanced.'
                      : 'Low light detected. Detection runs on the raw and a contrast-enhanced copy; recordings are unenhanced. Enhancement cannot recover detail the darkness removed.'
                  }
                  className="inline-flex items-center gap-1 rounded bg-indigo-600/90 px-1.5 py-0.5 text-[11px] font-bold tracking-wide text-white"
                >
                  <Moon className="h-3 w-3" />
                  {nightLabel}
                  {lighting.enhanced_view && ' · ENHANCED VIEW'}
                </span>
              )}
              {camera.recording && (
                <span className="inline-flex items-center gap-1.5 rounded bg-red-600/90 px-1.5 py-0.5 text-[11px] font-bold tracking-wide text-white">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />
                  REC
                </span>
              )}
            </div>
            {alerting && (
              <span
                className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-bold text-white ${
                  unknownCount > 0 ? 'bg-red-600/90' : knownNames.length > 0 ? 'bg-emerald-600/90' : 'bg-sky-600/90'
                }`}
              >
                <User className="h-3 w-3" />
                {people} · {percent(bestConfidence)}
              </span>
            )}
          </div>

          <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-2.5">
            {(knownNames.length > 0 || unknownCount > 0 || unsureCount > 0) && (
              <div className="mb-1.5 flex flex-wrap gap-1">
                {knownNames.map((name) => (
                  <span key={name} className="rounded bg-emerald-500/90 px-1.5 py-0.5 text-[11px] font-bold text-black">
                    {name}
                  </span>
                ))}
                {unknownCount > 0 && (
                  <span className="rounded bg-red-600 px-1.5 py-0.5 text-[11px] font-bold text-white">
                    {unknownCount} UNKNOWN
                  </span>
                )}
                {unsureCount > 0 && (
                  <span className="rounded bg-orange-500/90 px-1.5 py-0.5 text-[11px] font-bold text-black">
                    {unsureCount} NOT SURE
                  </span>
                )}
              </div>
            )}
            <div className="flex items-end justify-between gap-2">
              <p className="truncate text-sm font-semibold text-white drop-shadow">{camera.name}</p>
              <time className="font-mono text-xs tabular-nums text-slate-300">{formatClock(now)}</time>
            </div>
          </div>

          <button
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? 'Close full view' : 'Expand camera'}
            className="absolute right-2 top-10 rounded bg-black/60 p-1.5 text-slate-200 opacity-0 transition-opacity hover:bg-black/80 focus:opacity-100 group-hover:opacity-100"
          >
            {expanded ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </>
  )
}
