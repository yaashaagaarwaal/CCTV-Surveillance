import { Fragment, useState } from 'react'
import { Activity, Download, Play, Trash2 } from 'lucide-react'
import { api, downloadUrl } from '../api'
import { EventReasons, EventStatusBadge, EventTypeBadge, PeopleSummary } from '../components/EventBadges'
import Pagination from '../components/Pagination'
import VideoModal from '../components/VideoModal'
import { Card, ConfirmDialog, EmptyState, ErrorBanner, Spinner, inputClass } from '../components/ui'
import { useAuth } from '../hooks/useAuth'
import { useCameras } from '../hooks/useCameras'
import { usePolling } from '../hooks/usePolling'
import { formatDateTime, formatDuration, percent, timeAgo } from '../utils/format'

function EventActions({ event, onPlay, onDelete, canDelete }) {
  const disabledCls =
    'disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-slate-400'
  return (
    <div className="flex justify-end gap-1">
      <button
        onClick={() => onPlay(event)}
        disabled={!event.playable}
        aria-label="Play recording"
        className={`rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-sky-400 ${disabledCls}`}
      >
        <Play className="h-4 w-4" />
      </button>
      {event.playable ? (
        <a href={downloadUrl(event.id)} download aria-label="Download recording" className="rounded p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100">
          <Download className="h-4 w-4" />
        </a>
      ) : (
        <span className="p-1.5 text-slate-700">
          <Download className="h-4 w-4" />
        </span>
      )}
      {canDelete && <button
        onClick={() => onDelete(event)}
        disabled={event.status === 'recording'}
        aria-label="Delete event"
        className={`rounded p-1.5 text-slate-400 hover:bg-red-500/10 hover:text-red-400 ${disabledCls}`}
      >
        <Trash2 className="h-4 w-4" />
      </button>}
    </div>
  )
}

const PAGE_SIZE = 15

export default function EventsPage() {
  const { isAdmin } = useAuth()
  const { cameras, nameOf } = useCameras()
  const [filters, setFilters] = useState({ camera: '', type: '', status: '' })
  const [page, setPage] = useState(0)
  const [playing, setPlaying] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState(null)

  const { data, error, loading, refresh } = usePolling(
    () =>
      api.events({
        camera_id: filters.camera,
        event_type: filters.type,
        status: filters.status,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    5000,
    [filters.camera, filters.type, filters.status, page],
  )

  const items = data?.items ?? []
  const total = data?.total ?? 0


  const setFilter = (key, value) => {
    setFilters((f) => ({ ...f, [key]: value }))
    setPage(0)
  }

  const askDelete = (event) => {
    setDeleteError(null)
    setDeleting(event)
  }

  const confirmDelete = async () => {
    setDeleteBusy(true)
    setDeleteError(null)
    try {
      await api.deleteEvent(deleting.id)
      if (items.length === 1 && page > 0) setPage(page - 1)
      setDeleting(null)
      refresh()
    } catch (err) {
      setDeleteError(err.message)
    } finally {
      setDeleteBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Event history</h1>
        <p className="text-sm text-slate-500">Every motion and person detection, newest first</p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:max-w-3xl">
        <select className={inputClass} value={filters.camera} onChange={(e) => setFilter('camera', e.target.value)} aria-label="Filter by camera">
          <option value="">All cameras</option>
          {cameras.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select className={inputClass} value={filters.type} onChange={(e) => setFilter('type', e.target.value)} aria-label="Filter by type">
          <option value="">All event types</option>
          <option value="restricted_area">Restricted area</option>
          <option value="unknown_person">Unknown person</option>
          <option value="suspicious_activity">Suspicious activity</option>
          <option value="person">Person</option>
          <option value="motion">Motion only</option>
        </select>
        <select className={inputClass} value={filters.status} onChange={(e) => setFilter('status', e.target.value)} aria-label="Filter by status">
          <option value="">Any status</option>
          <option value="recording">Recording</option>
          <option value="completed">Completed</option>
          <option value="interrupted">Interrupted</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      <ErrorBanner>{error}</ErrorBanner>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner className="h-8 w-8" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState icon={Activity} title="No events found">
          Events appear here when a camera detects motion. Try clearing the filters.
        </EmptyState>
      ) : (
        <>
        <div className="space-y-3 sm:hidden">
          {items.map((event) => (
            <Card key={event.id} className="space-y-2 p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate font-medium">{nameOf(event.camera_id)}</p>
                <EventStatusBadge status={event.status} />
              </div>
              <p className="text-xs text-slate-400">
                {formatDateTime(event.timestamp)} · {timeAgo(event.timestamp)}
              </p>
              <PeopleSummary event={event} />
              <EventReasons event={event} limit={2} />
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <EventTypeBadge type={event.event_type} />
                  {event.max_confidence != null && <span>{percent(event.max_confidence)}</span>}
                  <span>· {formatDuration(event)}</span>
                </div>
                <EventActions event={event} onPlay={setPlaying} onDelete={askDelete} canDelete={isAdmin} />
              </div>
            </Card>
          ))}
        </div>

        <Card className="hidden overflow-hidden sm:block">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3 font-medium">Camera</th>
                  <th className="px-4 py-3 font-medium">Time</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="hidden px-4 py-3 font-medium lg:table-cell">Recognized</th>
                  <th className="hidden px-4 py-3 font-medium md:table-cell">Confidence</th>
                  <th className="hidden px-4 py-3 font-medium sm:table-cell">Duration</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {items.map((event) => (
                  <Fragment key={event.id}>
                  <tr className={`hover:bg-slate-800/30 ${event.reasons?.length ? 'border-b-0' : ''}`}>
                    <td className="px-4 py-3 font-medium">{nameOf(event.camera_id)}</td>
                    <td className="px-4 py-3 text-slate-400">
                      <span className="block text-slate-300">{formatDateTime(event.timestamp)}</span>
                      <span className="text-xs">{timeAgo(event.timestamp)}</span>
                    </td>
                    <td className="px-4 py-3">
                      <EventTypeBadge type={event.event_type} />
                    </td>
                    <td className="hidden px-4 py-3 lg:table-cell">
                      <PeopleSummary event={event} />
                    </td>
                    <td className="hidden px-4 py-3 tabular-nums text-slate-400 md:table-cell">{percent(event.max_confidence)}</td>
                    <td className="hidden px-4 py-3 tabular-nums text-slate-400 sm:table-cell">{formatDuration(event)}</td>
                    <td className="px-4 py-3">
                      <EventStatusBadge status={event.status} />
                    </td>
                    <td className="px-4 py-3">
                      <EventActions event={event} onPlay={setPlaying} onDelete={askDelete} canDelete={isAdmin} />
                    </td>
                  </tr>
                  {event.reasons?.length > 0 && (
                    <tr className="bg-slate-900/40">
                      <td colSpan={8} className="px-4 pb-3 pt-0">
                        <EventReasons event={event} limit={3} />
                      </td>
                    </tr>
                  )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        </>
      )}

      <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />

      {playing && <VideoModal event={playing} cameraName={nameOf(playing.camera_id)} onClose={() => setPlaying(null)} />}

      {deleting && (
        <ConfirmDialog
          title="Delete event"
          busy={deleteBusy}
          error={deleteError}
          onConfirm={confirmDelete}
          onCancel={() => setDeleting(null)}
        >
          Permanently delete this event from {nameOf(deleting.camera_id)} ({formatDateTime(deleting.timestamp)})
          {deleting.has_recording && ' and its recording file'}? This cannot be undone.
        </ConfirmDialog>
      )}
    </div>
  )
}
