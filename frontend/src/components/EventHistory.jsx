import { useEffect, useState } from 'react'
import EventPlayerModal from './EventPlayerModal'
import EventRow from './EventRow'

const POLL_INTERVAL_MS = 5000

function EventHistory() {
  const [events, setEvents] = useState([])
  const [cameraNames, setCameraNames] = useState({})
  const [error, setError] = useState(null)
  const [selectedEvent, setSelectedEvent] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const [eventsRes, camerasRes] = await Promise.all([
          fetch('/api/events?limit=50'),
          fetch('/api/cameras'),
        ])
        if (!eventsRes.ok) throw new Error(`status ${eventsRes.status}`)
        const eventsData = await eventsRes.json()
        const camerasData = camerasRes.ok ? await camerasRes.json() : []

        if (!cancelled) {
          setEvents(eventsData)
          setCameraNames(Object.fromEntries(camerasData.map((c) => [c.id, c.name])))
          setError(null)
        }
      } catch {
        if (!cancelled) setError('Could not reach backend for event history')
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

  if (events.length === 0) {
    return <p className="text-sm text-slate-500">No motion events recorded yet.</p>
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-slate-800 text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-2 font-medium">Camera</th>
              <th className="px-4 py-2 font-medium">Time</th>
              <th className="px-4 py-2 font-medium">Duration</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="px-4">
            {events.map((event) => (
              <EventRow
                key={event.id}
                event={event}
                cameraName={cameraNames[event.camera_id]}
                onView={setSelectedEvent}
              />
            ))}
          </tbody>
        </table>
      </div>

      <EventPlayerModal event={selectedEvent} onClose={() => setSelectedEvent(null)} />
    </>
  )
}

export default EventHistory
