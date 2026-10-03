import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, Film, Grid2x2, Grid3x3, RectangleHorizontal, Square, Users, Video } from 'lucide-react'
import { api } from '../api'
import AlertsPanel from '../components/AlertsPanel'
import CameraTile from '../components/CameraTile'
import RecentEvents from '../components/RecentEvents'
import RecordingCard from '../components/RecordingCard'
import StatCard from '../components/StatCard'
import VideoModal from '../components/VideoModal'
import { EmptyState, ErrorBanner, Spinner } from '../components/ui'
import { useCameras } from '../hooks/useCameras'
import { usePolling } from '../hooks/usePolling'

// Browsers cap simultaneous HTTP/1.1 connections per host (~6). Each live
// MJPEG feed holds one open, so beyond this many cameras the rest fall back
// to refreshing snapshots, keeping room for the dashboard's own API calls.
const MAX_LIVE_STREAMS = 4

const LAYOUTS = [
  { cols: 1, icon: RectangleHorizontal, label: '1 column', classes: 'grid-cols-1' },
  { cols: 2, icon: Square, label: '2 columns', classes: 'grid-cols-1 md:grid-cols-2' },
  { cols: 3, icon: Grid2x2, label: '3 columns', classes: 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3' },
  { cols: 4, icon: Grid3x3, label: '4 columns', classes: 'grid-cols-1 md:grid-cols-2 2xl:grid-cols-4' },
]

function loadCols() {
  try {
    const saved = Number(localStorage.getItem('dashboard.cols'))
    return LAYOUTS.some((l) => l.cols === saved) ? saved : 2
  } catch {
    return 2
  }
}

export default function DashboardPage() {
  const { cameras, loading, error: cameraError, nameOf } = useCameras()
  const summary = usePolling(api.summary, 3000)
  const recent = usePolling(() => api.events({ limit: 8 }), 4000)
  const recordings = usePolling(() => api.events({ recordings_only: true, limit: 4 }), 8000)

  const [cols, setCols] = useState(loadCols)
  const [playing, setPlaying] = useState(null)

  const chooseLayout = (value) => {
    setCols(value)
    try {
      localStorage.setItem('dashboard.cols', String(value))
    } catch {
      /* storage unavailable: layout just won't persist */
    }
  }

  const enabled = cameras.filter((c) => c.enabled)
  const liveIds = new Set(enabled.filter((c) => c.status === 'online').slice(0, MAX_LIVE_STREAMS).map((c) => c.id))
  const s = summary.data
  const gridClasses = LAYOUTS.find((l) => l.cols === cols).classes

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="text-sm text-slate-500">Live overview of every camera</p>
      </div>

      <ErrorBanner>{summary.error || cameraError}</ErrorBanner>

      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard
          icon={Video}
          label="Cameras online"
          value={s ? `${s.cameras.online}/${s.cameras.enabled}` : '—'}
          hint={s ? [s.cameras.offline ? `${s.cameras.offline} offline` : 'All connected', s.night_cameras ? `${s.night_cameras} in night mode` : null].filter(Boolean).join(' · ') : undefined}
          tone={s && s.cameras.offline ? 'amber' : 'green'}
        />
        <StatCard
          icon={Users}
          label="People detected now"
          value={s?.people_now ?? '—'}
          hint={s ? (s.people_now ? 'Live detection' : 'No one in view') : undefined}
          tone={s?.people_now ? 'red' : 'default'}
        />
        <StatCard
          icon={Activity}
          label="Events today"
          value={s?.events_today ?? '—'}
          hint={s ? `${s.person_events_today} with a person` : undefined}
          tone="blue"
        />
        <StatCard
          icon={Film}
          label="Recordings today"
          value={s?.recordings_today ?? '—'}
          hint={s ? (s.active_recordings ? `${s.active_recordings} recording now` : 'Not recording') : undefined}
          tone={s?.active_recordings ? 'red' : 'default'}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <section className="min-w-0 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Live cameras</h2>
            <div className="hidden items-center gap-1 rounded-lg border border-slate-800 p-0.5 md:flex">
              {LAYOUTS.map(({ cols: value, icon: Icon, label }) => (
                <button
                  key={value}
                  onClick={() => chooseLayout(value)}
                  aria-label={label}
                  title={label}
                  className={`rounded p-1.5 ${cols === value ? 'bg-slate-700 text-slate-100' : 'text-slate-500 hover:text-slate-200'}`}
                >
                  <Icon className="h-4 w-4" />
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <div className="flex justify-center py-16">
              <Spinner className="h-8 w-8" />
            </div>
          ) : enabled.length === 0 ? (
            <EmptyState icon={Video} title={cameras.length ? 'All cameras are disabled' : 'No cameras configured'}>
              <Link to="/cameras" className="text-sky-400 hover:underline">
                {cameras.length ? 'Enable a camera' : 'Add your first camera'}
              </Link>
            </EmptyState>
          ) : (
            <div className={`grid gap-4 ${gridClasses}`}>
              {enabled.map((camera) => (
                <CameraTile key={camera.id} camera={camera} live={liveIds.has(camera.id)} />
              ))}
            </div>
          )}
        </section>

        <aside className="min-w-0 space-y-6">
          <AlertsPanel liveAlerts={s?.alerts} nameOf={nameOf} />
          <RecentEvents events={recent.data?.items ?? []} nameOf={nameOf} onSelect={setPlaying} />
        </aside>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">Recent recordings</h2>
          <Link to="/recordings" className="text-xs text-sky-400 hover:underline">
            View all
          </Link>
        </div>
        {(recordings.data?.items ?? []).length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-800 py-8 text-center text-sm text-slate-500">
            No recordings yet.
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            {recordings.data.items.map((event) => (
              <RecordingCard key={event.id} event={event} cameraName={nameOf(event.camera_id)} onPlay={setPlaying} />
            ))}
          </div>
        )}
      </section>

      {playing && <VideoModal event={playing} cameraName={nameOf(playing.camera_id)} onClose={() => setPlaying(null)} />}
    </div>
  )
}
