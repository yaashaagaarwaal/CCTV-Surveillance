import { useRef, useState } from 'react'
import { Camera, CheckCircle2, ImagePlus, Info, Pencil, ScanFace, Trash2, UserPlus, X, XCircle } from 'lucide-react'
import { api, faceImageUrl } from '../api'
import CaptureFaceModal from '../components/CaptureFaceModal'
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorBanner, Modal, Spinner, inputClass } from '../components/ui'
import { useAuth } from '../hooks/useAuth'
import { useCameras } from '../hooks/useCameras'
import { usePolling } from '../hooks/usePolling'
import { formatDateTime, timeAgo } from '../utils/format'

const RECOMMENDED_PHOTOS = 3

function NameModal({ title, initial = '', submitLabel, onSubmit, onClose }) {
  const [name, setName] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onSubmit(name.trim())
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <input className={inputClass} value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="Full name" autoFocus />
        <ErrorBanner>{error}</ErrorBanner>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={!name.trim() || busy}>
            {busy && <Spinner className="h-4 w-4 text-white" />}
            {submitLabel}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function UploadResults({ results, onDismiss }) {
  return (
    <div className="space-y-1.5 rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-xs">
      <div className="flex items-center justify-between">
        <span className="font-medium text-slate-300">Upload results</span>
        <button onClick={onDismiss} aria-label="Dismiss results" className="text-slate-500 hover:text-slate-200">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      {results.map((r, i) => (
        <p key={i} className={`flex items-start gap-1.5 ${r.ok ? 'text-emerald-400' : 'text-red-400'}`}>
          {r.ok ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
          <span>
            <span className="font-medium">{r.filename}</span>
            {r.ok ? ' — added' : ` — ${r.error}`}
          </span>
        </p>
      ))}
    </div>
  )
}

function PersonCard({ person, cameras, available, canEdit, onChanged, onRename, onDelete }) {
  const fileInput = useRef(null)
  const [busy, setBusy] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [capturing, setCapturing] = useState(false)

  const upload = async (e) => {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    if (!files.length) return
    setBusy(true)
    setError(null)
    try {
      const response = await api.addFacePhotos(person.id, files)
      setResults(response.results)
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const removeSample = async (sample) => {
    setError(null)
    try {
      await api.deleteFaceSample(person.id, sample.id)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  const count = person.samples.length
  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold">{person.name}</p>
          <p className="text-xs text-slate-500">
            {person.last_seen ? `Last seen ${timeAgo(person.last_seen)} · ${formatDateTime(person.last_seen)}` : 'Not seen by a camera yet'}
          </p>
        </div>
        {canEdit && <div className="flex shrink-0 gap-1">
          <button onClick={() => onRename(person)} aria-label={`Rename ${person.name}`} className="rounded p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-100">
            <Pencil className="h-4 w-4" />
          </button>
          <button onClick={() => onDelete(person)} aria-label={`Delete ${person.name}`} className="rounded p-2 text-slate-400 hover:bg-red-500/10 hover:text-red-400">
            <Trash2 className="h-4 w-4" />
          </button>
        </div>}
      </div>

      <div>
        <div className="mb-2 flex items-center gap-2">
          <Badge tone={count >= RECOMMENDED_PHOTOS ? 'green' : 'amber'}>
            {count} {count === 1 ? 'photo' : 'photos'}
          </Badge>
          {count < RECOMMENDED_PHOTOS && (
            <span className="text-xs text-amber-400/90">Add at least {RECOMMENDED_PHOTOS} (different angles / lighting) for reliable recognition</span>
          )}
        </div>
        {count > 0 ? (
          <div className="flex flex-wrap gap-2">
            {person.samples.map((sample) => (
              <div key={sample.id} className="group relative">
                <img
                  src={faceImageUrl(person.id, sample.id)}
                  alt={`${person.name} face sample`}
                  title={`Detector confidence ${sample.quality} · ${sample.face_px}px face`}
                  className="h-16 w-16 rounded-lg object-cover"
                />
                {canEdit && <button
                  onClick={() => removeSample(sample)}
                  aria-label="Remove this photo"
                  className="absolute -right-1.5 -top-1.5 hidden rounded-full bg-red-600 p-0.5 text-white group-hover:block focus:block"
                >
                  <X className="h-3 w-3" />
                </button>}
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-lg border border-dashed border-slate-800 py-4 text-center text-xs text-slate-500">
            No face photos yet — this person can't be recognized
          </p>
        )}
      </div>

      {results && <UploadResults results={results} onDismiss={() => setResults(null)} />}
      <ErrorBanner>{error}</ErrorBanner>

      {canEdit && <div className="flex flex-wrap gap-2">
        <input ref={fileInput} type="file" accept="image/jpeg,image/png" multiple hidden onChange={upload} />
        <Button onClick={() => fileInput.current.click()} disabled={busy || !available}>
          {busy ? <Spinner className="h-4 w-4" /> : <ImagePlus className="h-4 w-4" />}
          Add photos
        </Button>
        <Button onClick={() => setCapturing(true)} disabled={busy || !available}>
          <Camera className="h-4 w-4" />
          Use camera
        </Button>
      </div>}

      {capturing && <CaptureFaceModal person={person} cameras={cameras} onCaptured={onChanged} onClose={() => setCapturing(false)} />}
    </Card>
  )
}

export default function PeoplePage() {
  const { isAdmin } = useAuth()
  const { cameras } = useCameras()
  const status = usePolling(api.recognitionStatus, 10000)
  const people = usePolling(api.people, 5000)
  const [naming, setNaming] = useState(null) // 'new' | person
  const [deleting, setDeleting] = useState(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState(null)

  const refreshAll = () => {
    people.refresh()
    status.refresh()
  }
  const available = status.data?.available ?? false
  const list = people.data ?? []

  const confirmDelete = async () => {
    setDeleteBusy(true)
    setDeleteError(null)
    try {
      await api.deletePerson(deleting.id)
      setDeleting(null)
      refreshAll()
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
          <h1 className="text-xl font-semibold">People</h1>
          <p className="text-sm text-slate-500">Register the people your cameras should recognize</p>
        </div>
        {isAdmin && (
          <Button variant="primary" onClick={() => setNaming('new')} disabled={!available}>
            <UserPlus className="h-4 w-4" />
            Register person
          </Button>
        )}
      </div>

      <ErrorBanner>{people.error || status.error}</ErrorBanner>

      {status.data && !available && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          Face recognition is not running ({status.data.enabled ? "its models couldn't be loaded — check the backend log" : 'it is turned off in settings'}).
          Cameras keep recording and detecting people normally.
        </div>
      )}

      {available && (
        <div className="flex gap-3 rounded-lg border border-slate-800 bg-slate-900/60 px-4 py-3 text-xs text-slate-400">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-400" />
          <div className="space-y-1">
            <p>
              A face is <span className="text-emerald-400">known</span> at similarity ≥ {status.data.known_threshold},{' '}
              <span className="text-red-400">unknown</span> below {status.data.unknown_threshold}, and{' '}
              <span className="text-orange-400">not confidently recognized</span> in between, when it is too small, or when the head
              is turned away. An unknown-person alert needs {status.data.unknown_confirmations} confirmations in one recording.
            </p>
            <p>Recognition is statistical and can be wrong — treat it as a helper, not proof of identity. Thresholds are configurable.</p>
            {status.data.people_count === 0 && (
              <p className="font-medium text-amber-300">
                No one is registered yet, so no unknown-person alerts are raised. Register at least one person to enable them.
              </p>
            )}
          </div>
        </div>
      )}

      {people.loading ? (
        <div className="flex justify-center py-16">
          <Spinner className="h-8 w-8" />
        </div>
      ) : list.length === 0 ? (
        <EmptyState icon={ScanFace} title="No one is registered">
          Register a person, then add a few clear, front-facing photos of just their face.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
          {list.map((person) => (
            <PersonCard
              key={person.id}
              person={person}
              cameras={cameras}
              available={available}
              canEdit={isAdmin}
              onChanged={refreshAll}
              onRename={setNaming}
              onDelete={(p) => {
                setDeleteError(null)
                setDeleting(p)
              }}
            />
          ))}
        </div>
      )}

      {naming && (
        <NameModal
          title={naming === 'new' ? 'Register person' : `Rename ${naming.name}`}
          initial={naming === 'new' ? '' : naming.name}
          submitLabel={naming === 'new' ? 'Register' : 'Save'}
          onClose={() => setNaming(null)}
          onSubmit={async (name) => {
            if (naming === 'new') await api.createPerson(name)
            else await api.renamePerson(naming.id, name)
            setNaming(null)
            refreshAll()
          }}
        />
      )}

      {deleting && (
        <ConfirmDialog
          title="Delete person"
          confirmLabel="Delete person"
          busy={deleteBusy}
          error={deleteError}
          onConfirm={confirmDelete}
          onCancel={() => setDeleting(null)}
        >
          Delete <strong>{deleting.name}</strong> and all of their face data ({deleting.samples.length} stored). They will no
          longer be recognized and will appear as an unknown person if seen again.
        </ConfirmDialog>
      )}
    </div>
  )
}
