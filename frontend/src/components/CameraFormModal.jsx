import { useEffect, useState } from 'react'
import { CheckCircle2, Plug, XCircle } from 'lucide-react'
import { api } from '../api'
import { Button, ErrorBanner, Modal, Spinner, inputClass } from './ui'

const TYPES = [
  { value: 'webcam', label: 'Local webcam', hint: 'Built-in or USB camera on this computer.' },
  { value: 'rtsp', label: 'RTSP / IP camera', hint: 'e.g. rtsp://user:pass@192.168.1.50:554/stream1' },
  { value: 'http', label: 'HTTP / MJPEG stream', hint: 'e.g. http://192.168.1.60:8080/video' },
  { value: 'file', label: 'Video file (loops)', hint: 'Simulates a camera from a video file — handy for testing.' },
]

function Field({ label, hint, children }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium text-slate-300">{label}</span>
      {children}
      {hint && <span className="block text-xs text-slate-500">{hint}</span>}
    </label>
  )
}

export default function CameraFormModal({ camera, onClose, onSaved }) {
  const editing = !!camera
  const [name, setName] = useState(camera?.name ?? '')
  const [type, setType] = useState(camera?.type ?? 'webcam')
  const [source, setSource] = useState(camera?.source ?? '0')
  const [enabled, setEnabled] = useState(camera?.enabled ?? true)
  const [files, setFiles] = useState(null)
  const [test, setTest] = useState(null)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (type !== 'file') return
    api
      .videoFiles()
      .then(setFiles)
      .catch((err) => setError(err.message))
  }, [type])

  const changeType = (value) => {
    setType(value)
    setSource(value === 'webcam' ? '0' : '')
    setTest(null)
  }

  const typeInfo = TYPES.find((t) => t.value === type)
  const canSubmit = name.trim() && source.trim() && !saving

  const runTest = async () => {
    setTesting(true)
    setTest(null)
    try {
      setTest(await api.testCamera({ type, source }))
    } catch (err) {
      setTest({ ok: false, error: err.message })
    } finally {
      setTesting(false)
    }
  }

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const body = { name: name.trim(), type, source: source.trim(), enabled }
      const saved = editing ? await api.updateCamera(camera.id, body) : await api.createCamera(body)
      onSaved(saved)
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <Modal title={editing ? `Edit ${camera.name}` : 'Add camera'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name">
          <input
            className={inputClass}
            value={name}
            maxLength={60}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Front Door"
            autoFocus
          />
        </Field>

        <Field label="Type" hint={typeInfo.hint}>
          <select className={inputClass} value={type} onChange={(e) => changeType(e.target.value)}>
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>

        {type === 'webcam' && (
          <Field label="Device index" hint="0 is the built-in webcam; try 1 for an external one.">
            <input
              className={inputClass}
              type="number"
              min="0"
              value={source}
              onChange={(e) => {
                setSource(e.target.value)
                setTest(null)
              }}
            />
          </Field>
        )}

        {type === 'file' && (
          <Field
            label="Video file"
            hint={
              files && files.files.length === 0
                ? `No videos found. Run "python scripts/make_demo_videos.py" in the backend folder, or copy .mp4 files into ${files.directory}`
                : undefined
            }
          >
            <select
              className={inputClass}
              value={source}
              onChange={(e) => {
                setSource(e.target.value)
                setTest(null)
              }}
            >
              <option value="">Select a video…</option>
              {(files?.files ?? []).map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
              {source && files && !files.files.includes(source) && <option value={source}>{source}</option>}
            </select>
          </Field>
        )}

        {(type === 'rtsp' || type === 'http') && (
          <Field label="Stream URL">
            <input
              className={inputClass}
              value={source}
              onChange={(e) => {
                setSource(e.target.value)
                setTest(null)
              }}
              placeholder={type === 'rtsp' ? 'rtsp://user:pass@192.168.1.50:554/stream1' : 'http://192.168.1.60:8080/video'}
              spellCheck={false}
              autoComplete="off"
            />
          </Field>
        )}

        <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="h-4 w-4 accent-sky-500" />
          Enabled (start streaming and recording immediately)
        </label>

        <div className="space-y-2">
          <Button onClick={runTest} disabled={!source.trim() || testing}>
            {testing ? <Spinner className="h-4 w-4" /> : <Plug className="h-4 w-4" />}
            Test connection
          </Button>
          {test?.ok && (
            <p className="flex items-center gap-2 text-sm text-emerald-400">
              <CheckCircle2 className="h-4 w-4" /> Connected — {test.width}×{test.height}
            </p>
          )}
          {test && !test.ok && (
            <p className="flex items-start gap-2 text-sm text-red-400">
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" /> {test.error}
            </p>
          )}
        </div>

        <ErrorBanner>{error}</ErrorBanner>

        <div className="flex justify-end gap-2 border-t border-slate-800 pt-4">
          <Button onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={!canSubmit}>
            {saving && <Spinner className="h-4 w-4 text-white" />}
            {editing ? 'Save changes' : 'Add camera'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
