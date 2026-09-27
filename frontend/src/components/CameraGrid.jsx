import { useEffect, useState } from 'react'
import CameraCard from './CameraCard'

const POLL_INTERVAL_MS = 3000

function CameraGrid() {
  const [cameras, setCameras] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const res = await fetch('/api/cameras')
        if (!res.ok) throw new Error(`status ${res.status}`)
        const data = await res.json()
        if (!cancelled) {
          setCameras(data)
          setError(null)
        }
      } catch {
        if (!cancelled) setError('Could not reach backend for camera status')
      }
    }

    poll()
    const intervalId = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(intervalId)
    }
  }, [])

  if (error) {
    return <p className="text-sm text-red-400">{error}</p>
  }

  if (cameras.length === 0) {
    return <p className="text-sm text-slate-500">No cameras configured.</p>
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {cameras.map((camera) => (
        <CameraCard key={camera.id} camera={camera} />
      ))}
    </div>
  )
}

export default CameraGrid
