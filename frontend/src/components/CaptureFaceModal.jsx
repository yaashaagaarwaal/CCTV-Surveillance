import { useState } from 'react'
import { Camera, CheckCircle2 } from 'lucide-react'
import { api, snapshotUrl } from '../api'
import { useNow } from '../hooks/useNow'
import { Button, ErrorBanner, Modal, Spinner, inputClass } from './ui'

// Register a face straight from a live camera: the person looks at the camera
// and you capture. Repeat from different angles / lighting for best results.
export default function CaptureFaceModal({ person, cameras, onCaptured, onClose }) {
  const online = cameras.filter((c) => c.status === 'online')
  const [cameraId, setCameraId] = useState(online[0]?.id ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [captured, setCaptured] = useState(0)
  const tick = useNow(1000).getTime()

  const capture = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.addFaceFromCamera(person.id, cameraId)
      setCaptured((n) => n + 1)
      onCaptured()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={`Capture a face for ${person.name}`} onClose={onClose}>
      <div className="space-y-4">
        {online.length === 0 ? (
          <ErrorBanner>No camera is online right now.</ErrorBanner>
        ) : (
          <>
            <select className={inputClass} value={cameraId} onChange={(e) => setCameraId(e.target.value)} aria-label="Camera">
              {online.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <div className="aspect-video overflow-hidden rounded-lg bg-black">
              {cameraId && <img src={`${snapshotUrl(cameraId)}?t=${tick}`} alt="Camera preview" className="h-full w-full object-contain" />}
            </div>
            <p className="text-xs text-slate-500">
              Ask {person.name} to face the camera, close and well lit, with only their face in view. Capture a few times with
              slightly different angles and lighting.
            </p>
          </>
        )}
        <ErrorBanner>{error}</ErrorBanner>
        {captured > 0 && (
          <p className="flex items-center gap-2 text-sm text-emerald-400">
            <CheckCircle2 className="h-4 w-4" /> {captured} {captured === 1 ? 'photo' : 'photos'} added
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Done</Button>
          <Button variant="primary" onClick={capture} disabled={!cameraId || busy}>
            {busy ? <Spinner className="h-4 w-4 text-white" /> : <Camera className="h-4 w-4" />}
            Capture face
          </Button>
        </div>
      </div>
    </Modal>
  )
}
