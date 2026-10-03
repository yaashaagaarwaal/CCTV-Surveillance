import { api } from '../api'
import { usePolling } from './usePolling'

const EMPTY = []

// Live camera list (status, people count, recording flag) refreshed every 3s,
// plus an id -> name lookup used by every page that shows events.
export function useCameras() {
  const { data, error, loading, refresh } = usePolling(api.cameras, 3000)
  const cameras = data ?? EMPTY
  const names = Object.fromEntries(cameras.map((c) => [c.id, c.name]))
  const nameOf = (id) => names[id] ?? 'Deleted camera'
  return { cameras, error, loading, refresh, nameOf }
}
