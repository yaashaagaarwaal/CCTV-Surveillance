import { useState } from 'react'
import { Film } from 'lucide-react'
import { api } from '../api'
import Pagination from '../components/Pagination'
import RecordingCard from '../components/RecordingCard'
import VideoModal from '../components/VideoModal'
import { ConfirmDialog, EmptyState, ErrorBanner, Spinner, inputClass } from '../components/ui'
import { useAuth } from '../hooks/useAuth'
import { useCameras } from '../hooks/useCameras'
import { usePolling } from '../hooks/usePolling'
import { formatDateTime } from '../utils/format'

const PAGE_SIZE = 12

export default function RecordingsPage() {
  const { isAdmin } = useAuth()
  const { cameras, nameOf } = useCameras()
  const [camera, setCamera] = useState('')
  const [type, setType] = useState('')
  const [page, setPage] = useState(0)
  const [playing, setPlaying] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState(null)

  const { data, error, loading, refresh } = usePolling(
    () =>
      api.events({
        recordings_only: true,
        camera_id: camera,
        event_type: type,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    8000,
    [camera, type, page],
  )

  const items = data?.items ?? []
  const total = data?.total ?? 0


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
        <h1 className="text-xl font-semibold">Recordings</h1>
        <p className="text-sm text-slate-500">
          {data ? `${total} saved ${total === 1 ? 'clip' : 'clips'}` : 'Saved clips'} — play, download or delete
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:max-w-xl">
        <select
          className={inputClass}
          value={camera}
          onChange={(e) => {
            setCamera(e.target.value)
            setPage(0)
          }}
          aria-label="Filter by camera"
        >
          <option value="">All cameras</option>
          {cameras.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          className={inputClass}
          value={type}
          onChange={(e) => {
            setType(e.target.value)
            setPage(0)
          }}
          aria-label="Filter by type"
        >
          <option value="">All clips</option>
          <option value="restricted_area">Restricted area</option>
          <option value="unknown_person">Unknown person</option>
          <option value="suspicious_activity">Suspicious activity</option>
          <option value="person">With a person</option>
          <option value="motion">Motion only</option>
        </select>
      </div>

      <ErrorBanner>{error}</ErrorBanner>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner className="h-8 w-8" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState icon={Film} title="No recordings found">
          Clips are saved automatically whenever motion is detected.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {items.map((event) => (
            <RecordingCard
              key={event.id}
              event={event}
              cameraName={nameOf(event.camera_id)}
              onPlay={setPlaying}
              onDelete={
                isAdmin
                  ? (e) => {
                      setDeleteError(null)
                      setDeleting(e)
                    }
                  : undefined
              }
            />
          ))}
        </div>
      )}

      <Pagination page={page} pageSize={PAGE_SIZE} total={total} onChange={setPage} />

      {playing && <VideoModal event={playing} cameraName={nameOf(playing.camera_id)} onClose={() => setPlaying(null)} />}

      {deleting && (
        <ConfirmDialog
          title="Delete recording"
          busy={deleteBusy}
          error={deleteError}
          onConfirm={confirmDelete}
          onCancel={() => setDeleting(null)}
        >
          Permanently delete the clip from {nameOf(deleting.camera_id)} ({formatDateTime(deleting.timestamp)}) and its
          event record? This cannot be undone.
        </ConfirmDialog>
      )}
    </div>
  )
}
