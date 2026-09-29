const STATUS_STYLES = {
  recording: 'bg-yellow-500/20 text-yellow-400',
  completed: 'bg-green-500/20 text-green-400',
  failed: 'bg-red-500/20 text-red-400',
  interrupted: 'bg-orange-500/20 text-orange-400',
}

function formatDuration(event) {
  if (!event.ended_at) return event.status === 'recording' ? 'in progress…' : '—'
  const seconds = Math.round((new Date(event.ended_at) - new Date(event.timestamp)) / 1000)
  return `${seconds}s`
}

function EventRow({ event, cameraName, onView }) {
  return (
    <tr className="border-b border-slate-800 last:border-0">
      <td className="py-2 pr-4 text-sm text-slate-300">{cameraName ?? event.camera_id}</td>
      <td className="py-2 pr-4 text-sm text-slate-400">
        {new Date(event.timestamp).toLocaleString()}
      </td>
      <td className="py-2 pr-4 text-sm text-slate-400">{formatDuration(event)}</td>
      <td className="py-2 pr-4">
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium uppercase ${
            STATUS_STYLES[event.status] ?? 'bg-slate-700 text-slate-300'
          }`}
        >
          {event.status}
        </span>
      </td>
      <td className="py-2 text-right">
        <button
          onClick={() => onView(event)}
          disabled={!event.has_recording}
          className="text-sm text-blue-400 hover:underline disabled:cursor-not-allowed disabled:text-slate-600 disabled:no-underline"
        >
          View
        </button>
      </td>
    </tr>
  )
}

export default EventRow
