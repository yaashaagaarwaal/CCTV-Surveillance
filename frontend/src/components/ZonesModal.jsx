import { useEffect, useRef, useState } from 'react'
import { Eraser, MousePointerClick, Plus, Trash2, Undo2 } from 'lucide-react'
import { api, snapshotUrl } from '../api'
import { Badge, Button, ErrorBanner, Modal, Spinner, inputClass } from './ui'

const SEVERITY_OPTIONS = ['medium', 'high', 'critical']

function polygonPoints(points) {
  return points.map(([x, y]) => `${x},${y}`).join(' ')
}

/**
 * Draw restricted zones on a camera's picture. Click to place the corners of a
 * shape (3 or more); a person whose feet are inside an active zone raises a
 * "restricted area" alert. Coordinates are stored as fractions of the frame, so
 * they survive a change of camera resolution.
 */
export default function ZonesModal({ camera, canEdit, onClose }) {
  const [zones, setZones] = useState(null)
  const [draft, setDraft] = useState([])
  const [name, setName] = useState('')
  const [severity, setSeverity] = useState('high')
  const [scheduled, setScheduled] = useState(false)
  const [start, setStart] = useState('22:00')
  const [end, setEnd] = useState('06:00')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [imageFailed, setImageFailed] = useState(false)
  const canvas = useRef(null)
  const online = camera.status === 'online'

  const load = () =>
    api
      .zones(camera.id)
      .then(setZones)
      .catch((err) => setError(err.message))
  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const addPoint = (e) => {
    if (!canEdit) return
    const rect = canvas.current.getBoundingClientRect()
    const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
    const y = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height))
    setDraft((points) => [...points, [Number(x.toFixed(4)), Number(y.toFixed(4))]])
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.createZone(camera.id, {
        name: name.trim(),
        points: draft,
        severity,
        schedule_start: scheduled ? start : null,
        schedule_end: scheduled ? end : null,
      })
      setDraft([])
      setName('')
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (zone) => {
    setError(null)
    try {
      await api.deleteZone(zone.id)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <Modal title={`Restricted zones — ${camera.name}`} onClose={onClose} wide>
      <div className="space-y-4">
        <div
          ref={canvas}
          onClick={addPoint}
          className={`relative aspect-video overflow-hidden rounded-lg bg-slate-950 ${canEdit ? 'cursor-crosshair' : ''}`}
        >
          {online && !imageFailed ? (
            <img src={`${snapshotUrl(camera.id)}?t=${camera.id}`} alt="" onError={() => setImageFailed(true)} className="h-full w-full object-cover" draggable={false} />
          ) : (
            <div className="flex h-full items-center justify-center px-6 text-center text-sm text-slate-500">
              The camera is offline, so there's no picture to draw on. You can still place zones on this blank frame.
            </div>
          )}
          {/* viewBox 0..1 with non-uniform scaling: points are fractions of the frame */}
          <svg viewBox="0 0 1 1" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 h-full w-full">
            {(zones ?? []).map((zone) => (
              <polygon key={zone.id} points={polygonPoints(zone.points)} fill="rgba(239,68,68,0.22)" stroke="#ef4444" strokeWidth="0.004" vectorEffect="non-scaling-stroke" />
            ))}
            {draft.length >= 2 && <polyline points={polygonPoints(draft)} fill="rgba(56,189,248,0.2)" stroke="#38bdf8" strokeWidth="2" vectorEffect="non-scaling-stroke" />}
            {draft.map(([x, y], i) => (
              <circle key={i} cx={x} cy={y} r="0.008" fill="#38bdf8" />
            ))}
          </svg>
          {canEdit && draft.length === 0 && (
            <span className="pointer-events-none absolute left-2 top-2 flex items-center gap-1.5 rounded bg-black/70 px-2 py-1 text-xs text-slate-200">
              <MousePointerClick className="h-3.5 w-3.5" /> Click the picture to place the corners of a zone
            </span>
          )}
        </div>

        {canEdit && draft.length > 0 && (
          <div className="space-y-3 rounded-lg border border-slate-800 p-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <input className={inputClass} placeholder="Zone name, e.g. Driveway" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} />
              <select className={inputClass} value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Alert severity">
                {SEVERITY_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    Alert severity: {s}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
              <input type="checkbox" checked={scheduled} onChange={(e) => setScheduled(e.target.checked)} className="h-4 w-4 accent-sky-500" />
              Only enforce during certain hours
            </label>
            {scheduled && (
              <div className="flex items-center gap-2 text-sm text-slate-300">
                from <input type="time" className={`${inputClass} w-auto`} value={start} onChange={(e) => setStart(e.target.value)} />
                to <input type="time" className={`${inputClass} w-auto`} value={end} onChange={(e) => setEnd(e.target.value)} />
                <span className="text-xs text-slate-500">(may cross midnight)</span>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => setDraft((p) => p.slice(0, -1))}>
                <Undo2 className="h-4 w-4" /> Undo point
              </Button>
              <Button onClick={() => setDraft([])}>
                <Eraser className="h-4 w-4" /> Clear
              </Button>
              <Button variant="primary" onClick={save} disabled={draft.length < 3 || !name.trim() || busy}>
                {busy ? <Spinner className="h-4 w-4 text-white" /> : <Plus className="h-4 w-4" />}
                Save zone ({draft.length} points)
              </Button>
            </div>
          </div>
        )}

        <ErrorBanner>{error}</ErrorBanner>

        <div>
          <p className="mb-2 text-sm font-medium text-slate-300">Zones on this camera</p>
          {zones === null ? (
            <Spinner className="h-5 w-5" />
          ) : zones.length === 0 ? (
            <p className="text-sm text-slate-500">None yet.</p>
          ) : (
            <ul className="divide-y divide-slate-800 rounded-lg border border-slate-800">
              {zones.map((zone) => (
                <li key={zone.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                  <span className="min-w-0">
                    <span className="font-medium">{zone.name}</span>
                    <span className="ml-2 text-xs text-slate-500">
                      {zone.schedule_start ? `${zone.schedule_start}–${zone.schedule_end}` : 'always'} · {zone.points.length} points
                    </span>
                  </span>
                  <span className="flex items-center gap-2">
                    <Badge tone={zone.severity === 'medium' ? 'amber' : 'red'}>{zone.severity}</Badge>
                    {canEdit && (
                      <button onClick={() => remove(zone)} aria-label={`Delete zone ${zone.name}`} className="rounded p-1.5 text-slate-400 hover:bg-red-500/10 hover:text-red-400">
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <p className="text-xs text-slate-500">
          A person counts as inside a zone when their feet (the bottom-centre of their detected box) are inside it, for two detection cycles in a row. Detection runs while the
          camera sees motion, so someone standing perfectly still for a long time may stop being checked.
        </p>
      </div>
    </Modal>
  )
}
