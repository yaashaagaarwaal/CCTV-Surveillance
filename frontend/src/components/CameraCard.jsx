const STATUS_STYLES = {
  online: 'bg-green-500',
  connecting: 'bg-yellow-500',
  offline: 'bg-red-500',
}

function CameraCard({ camera }) {
  const isOnline = camera.status === 'online'

  return (
    <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-900">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <span className="font-medium">{camera.name}</span>
        <span className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-400">
          <span
            className={`h-2 w-2 rounded-full ${STATUS_STYLES[camera.status] ?? 'bg-slate-600'}`}
          />
          {camera.status}
        </span>
      </div>

      <div className="flex aspect-video items-center justify-center bg-black">
        {isOnline ? (
          // Keyed on id+status so a fresh <img> mounts (and opens a new
          // stream request) whenever the camera transitions to online.
          <img
            key={`${camera.id}-online`}
            src={`/api/cameras/${camera.id}/stream`}
            alt={camera.name}
            className="h-full w-full object-contain"
          />
        ) : (
          <span className="text-sm text-slate-500">
            {camera.status === 'connecting' ? 'Connecting…' : 'Camera offline'}
          </span>
        )}
      </div>
    </div>
  )
}

export default CameraCard
