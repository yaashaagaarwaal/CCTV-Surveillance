import { useCallback, useEffect, useState } from 'react'

// Calls `fetcher` immediately and then every `intervalMs`. Re-runs (and
// keeps showing the previous data meanwhile) when `deps` change, and exposes
// `refresh()` for "I just changed something" moments.
export function usePolling(fetcher, intervalMs, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)

  const refresh = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false

    async function tick() {
      try {
        const result = await fetcher()
        if (!cancelled) {
          setData(result)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    tick()
    const id = setInterval(tick, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, reloadKey, ...deps])

  return { data, error, loading, refresh }
}
