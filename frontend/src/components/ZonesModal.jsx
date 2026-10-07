import { useEffect, useRef, useState } from 'react'
import { Eraser, MousePointerClick, Plus, Save, Trash2, Undo2 } from 'lucide-react'
import { api, snapshotUrl } from '../api'
import { Badge, Button, ErrorBanner, Modal, Spinner, inputClass } from './ui'

// inputClass is full-width; the small numeric fields sit inline in a sentence instead
const inlineInput = (width) => inputClass.replace('w-full', width)

const SEVERITY_OPTIONS = ['medium', 'high', 'critical']

function polygonPoints(points) {
  return points.map(([x, y]) => `${x},${y}`).join(' ')
}

function describeRules(zone) {
  const parts = []
  if (zone.loiter_seconds > 0) parts.push(`loitering after ${zone.loiter_seconds} s`)
  if (zone.repeat_entries > 0) parts.push(`${zone.repeat_entries} entries in ${Math.round(zone.repeat_window_seconds / 60)} min`)
  return parts.length ? parts.join(' · ') : 'intrusion only'
}

/** Security hours and fall detection for one camera (not tied to a zone). */
function CameraRules({ camera, canEdit }) {
  const [rules, setRules] = useState(null)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .rules(camera.id)
      .then(setRules)
      .catch((err) => setMessage({ ok: false, text: err.message }))
  }, [camera.id])

  if (!rules) return message ? <ErrorBanner>{message.text}</ErrorBanner> : <Spinner className="h-5 w-5" />
  const hoursOn = Boolean(rules.quiet_start && rules.quiet_end)
  const patch = (changes) => {
    setMessage(null)
    setRules((r) => ({ ...r, ...changes }))
  }
  const save = async () => {
    setBusy(true)
    setMessage(null)
    try {
      setRules(await api.setRules(camera.id, rules))
      setMessage({ ok: true, text: 'Saved.' })
    } catch (err) {
      setMessage({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-800 p-3">
      <p className="text-sm font-medium text-slate-300">Other security rules for this camera</p>
      <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
        <input
          type="checkbox"
          disabled={!canEdit}
          checked={hoursOn}
          onChange={(e) => patch(e.target.checked ? { quiet_start: '23:00', quiet_end: '05:00' } : { quiet_start: null, quiet_end: null })}
          className="h-4 w-4 accent-sky-500"
        />
        Alert when a person is seen during security hours
      </label>
      {hoursOn && (
        <div className="flex items-center gap-2 pl-6 text-sm text-slate-300">
          from <input type="time" disabled={!canEdit} className={inlineInput('w-auto')} value={rules.quiet_start} onChange={(e) => patch({ quiet_start: e.target.value })} />
          to <input type="time" disabled={!canEdit} className={inlineInput('w-auto')} value={rules.quiet_end} onChange={(e) => patch({ quiet_end: e.target.value })} />
          <span className="text-xs text-slate-500">(server's local time; may cross midnight)</span>
        </div>
      )}
      <label className="flex cursor-pointer items-start gap-2 text-sm text-slate-300">
        <input type="checkbox" disabled={!canEdit} checked={rules.fall_detection} onChange={(e) => patch({ fall_detection: e.target.checked })} className="mt-0.5 h-4 w-4 accent-sky-500" />
        <span>
          Watch for fall-like movement
          <span className="block text-xs text-slate-500">
            Experimental. Judged from the person's outline only: it flags someone who goes from upright to lying within a few seconds and stays down. It misses falls that are
            partly hidden or seen from above, and can fire when someone lies down quickly on purpose.
          </span>
        </span>
      </label>
      {canEdit && (
        <div className="flex items-center gap-3">
          <Button variant="primary" onClick={save} disabled={busy}>
            {busy ? <Spinner className="h-4 w-4 text-white" /> : <Save className="h-4 w-4" />} Save rules
          </Button>
          {message && <span className={`text-xs ${message.ok ? 'text-emerald-400' : 'text-red-400'}`}>{message.text}</span>}
        </div>
      )}
    </div>
  )
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
  const [loiterOn, setLoiterOn] = useState(true)
  const [loiterSeconds, setLoiterSeconds] = useState(30)
  const [repeatOn, setRepeatOn] = useState(true)
  const [repeatEntries, setRepeatEntries] = useState(3)
  const [repeatMinutes, setRepeatMinutes] = useState(5)
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
        loiter_seconds: loiterOn ? Number(loiterSeconds) : 0,
        repeat_entries: repeatOn ? Number(repeatEntries) : 0,
        repeat_window_seconds: Math.round(Number(repeatMinutes) * 60),
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
    <Modal title={`Zones & security rules — ${camera.name}`} onClose={onClose} wide>
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

        {canEdit && (
          // Always shown (greyed out until a corner is placed) so the picture doesn't jump while drawing.
          <fieldset disabled={draft.length === 0} className="space-y-3 rounded-lg border border-slate-800 p-3 disabled:opacity-50">
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
                from <input type="time" className={inlineInput('w-auto')} value={start} onChange={(e) => setStart(e.target.value)} />
                to <input type="time" className={inlineInput('w-auto')} value={end} onChange={(e) => setEnd(e.target.value)} />
                <span className="text-xs text-slate-500">(may cross midnight)</span>
              </div>
            )}
            <div className="space-y-2 text-sm text-slate-300">
              <label className="flex flex-wrap items-center gap-2">
                <input type="checkbox" checked={loiterOn} onChange={(e) => setLoiterOn(e.target.checked)} className="h-4 w-4 accent-sky-500" />
                Loitering alert if someone stays inside for
                <input type="number" min="5" max="3600" disabled={!loiterOn} className={inlineInput('w-20')} value={loiterSeconds} onChange={(e) => setLoiterSeconds(e.target.value)} />
                seconds
              </label>
              <label className="flex flex-wrap items-center gap-2">
                <input type="checkbox" checked={repeatOn} onChange={(e) => setRepeatOn(e.target.checked)} className="h-4 w-4 accent-sky-500" />
                Repeated-entry alert after
                <input type="number" min="2" max="20" disabled={!repeatOn} className={inlineInput('w-16')} value={repeatEntries} onChange={(e) => setRepeatEntries(e.target.value)} />
                entries within
                <input type="number" min="1" max="1440" disabled={!repeatOn} className={inlineInput('w-20')} value={repeatMinutes} onChange={(e) => setRepeatMinutes(e.target.value)} />
                minutes
              </label>
            </div>
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
          </fieldset>
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
                      {zone.schedule_start ? `${zone.schedule_start}–${zone.schedule_end}` : 'always'} · {describeRules(zone)}
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
        <CameraRules camera={camera} canEdit={canEdit} />

        <p className="text-xs text-slate-500">
          A person counts as inside a zone when their feet (the bottom-centre of their detected box) are inside it, for two detection cycles in a row, and as having left once the zone has been empty for a few seconds. Detection runs while the
          camera sees motion, so someone standing perfectly still for a long time may stop being checked.
        </p>
      </div>
    </Modal>
  )
}
