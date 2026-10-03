import { useState } from 'react'
import { Moon, Pencil, Plus, Trash2, Video, VideoOff } from 'lucide-react'
import { OctagonAlert } from 'lucide-react'
import { api, snapshotUrl } from '../api'
import CameraFormModal from '../components/CameraFormModal'
import ZonesModal from '../components/ZonesModal'
import { useAuth } from '../hooks/useAuth'
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorBanner, Spinner, StatusBadge } from '../components/ui'
import { useCameras } from '../hooks/useCameras'
import { useNow } from '../hooks/useNow'

const TYPE_LABELS = { webcam: 'Webcam', rtsp: 'RTSP', http: 'HTTP', file: 'Video file' }

function Toggle({ checked, onChange, disabled, label }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50 ${checked ? 'bg-sky-600' : 'bg-slate-700'}`}
    >
      <span className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${checked ? 'translate-x-5' : ''}`} />
    </button>
  )
}

function CameraRow({ camera, tick, busy, canEdit, onToggle, onEdit, onDelete, onZones }) {
  const online = camera.status === 'online'
  return (
    <Card className="overflow-hidden">
      <div className="relative aspect-video bg-slate-950">
        {online ? (
          <img src={`${snapshotUrl(camera.id)}?t=${tick}`} alt={camera.name} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-slate-600">
            <VideoOff className="h-8 w-8" />
            <span className="text-xs">{camera.status === 'disabled' ? 'Disabled' : 'No signal'}</span>
          </div>
        )}
      </div>

      <div className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate font-semibold">{camera.name}</p>
            <p className="truncate font-mono text-xs text-slate-500" title={camera.source_display}>
              {camera.source_display}
            </p>
          </div>
          <StatusBadge status={camera.status} />
        </div>

        <div className="flex items-center gap-2">
          <Badge>{TYPE_LABELS[camera.type] ?? camera.type}</Badge>
          {camera.recording && <Badge tone="red">Recording</Badge>}
          {camera.people_detected > 0 && <Badge tone="blue">{camera.people_detected} in view</Badge>}
          {camera.lighting?.night && (
            <Badge tone="blue">
              <Moon className="h-3 w-3" /> {camera.lighting.kind === 'infrared' ? 'Night · IR' : 'Night mode'}
            </Badge>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-slate-800 pt-3">
          <label className="flex items-center gap-2 text-sm text-slate-400">
            <Toggle checked={camera.enabled} disabled={busy || !canEdit} onChange={(v) => onToggle(camera, v)} label={`Enable ${camera.name}`} />
            {camera.enabled ? 'Enabled' : 'Disabled'}
          </label>
          <div className="flex gap-1">
            <button onClick={() => onZones(camera)} aria-label={`Restricted zones for ${camera.name}`} title="Restricted zones" className="rounded p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-100">
              <OctagonAlert className="h-4 w-4" />
            </button>
            {canEdit && (
              <>
                <button onClick={() => onEdit(camera)} aria-label={`Edit ${camera.name}`} className="rounded p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-100">
                  <Pencil className="h-4 w-4" />
                </button>
                <button onClick={() => onDelete(camera)} aria-label={`Delete ${camera.name}`} className="rounded p-2 text-slate-400 hover:bg-red-500/10 hover:text-red-400">
                  <Trash2 className="h-4 w-4" />
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </Card>
  )
}

export default function CamerasPage() {
  const { isAdmin } = useAuth()
  const [zonesFor, setZonesFor] = useState(null)
  const { cameras, loading, error, refresh } = useCameras()
  const tick = useNow(3000).getTime()
  const [form, setForm] = useState(null) // null | 'new' | camera
  const [deleting, setDeleting] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState(null)

  const toggle = async (camera, enabled) => {
    setBusyId(camera.id)
    setActionError(null)
    try {
      await api.updateCamera(camera.id, { enabled })
      refresh()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  const confirmDelete = async () => {
    setDeleteBusy(true)
    setDeleteError(null)
    try {
      await api.deleteCamera(deleting.id)
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Cameras</h1>
          <p className="text-sm text-slate-500">Add, edit and monitor every camera source</p>
        </div>
        {isAdmin && (
          <Button variant="primary" onClick={() => setForm('new')}>
            <Plus className="h-4 w-4" />
            Add camera
          </Button>
        )}
      </div>

      <ErrorBanner>{error || actionError}</ErrorBanner>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner className="h-8 w-8" />
        </div>
      ) : cameras.length === 0 ? (
        <EmptyState icon={Video} title="No cameras yet">
          Add a local webcam, an RTSP/IP camera, or a looping video file to get started.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cameras.map((camera) => (
            <CameraRow
              key={camera.id}
              camera={camera}
              tick={tick}
              busy={busyId === camera.id}
              canEdit={isAdmin}
              onZones={setZonesFor}
              onToggle={toggle}
              onEdit={setForm}
              onDelete={(c) => {
                setDeleteError(null)
                setDeleting(c)
              }}
            />
          ))}
        </div>
      )}

      {zonesFor && <ZonesModal camera={zonesFor} canEdit={isAdmin} onClose={() => setZonesFor(null)} />}

      {form && (
        <CameraFormModal
          camera={form === 'new' ? null : form}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null)
            refresh()
          }}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete camera"
          confirmLabel="Delete camera"
          busy={deleteBusy}
          error={deleteError}
          onConfirm={confirmDelete}
          onCancel={() => setDeleting(null)}
        >
          Delete <strong>{deleting.name}</strong>? Its live stream stops immediately. Existing events and recordings
          are kept.
        </ConfirmDialog>
      )}
    </div>
  )
}
