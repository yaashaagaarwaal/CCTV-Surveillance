import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { ALERT_TYPES } from '../utils/meta'
import { AlertsContext } from './useAlerts'
import { usePolling } from './usePolling'

const NOTIFY_KEY = 'notify.browser'
const MAX_BACKOFF_MS = 30000

function browserNotificationsSupported() {
  return typeof window !== 'undefined' && 'Notification' in window
}

function loadNotifyPreference() {
  try {
    return localStorage.getItem(NOTIFY_KEY) === '1' && browserNotificationsSupported() && Notification.permission === 'granted'
  } catch {
    return false
  }
}

// One shared source of alert state for the whole app:
//  - a WebSocket pushes new/updated alerts the moment they happen (real time),
//  - a slow poll is the safety net if the socket is down,
//  - optional browser notifications fire when the tab isn't focused.
export function AlertsProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const [connection, setConnection] = useState('connecting') // connecting | live | reconnecting
  const [notifyBrowser, setNotifyBrowser] = useState(loadNotifyPreference)
  const notifyRef = useRef(notifyBrowser)
  useEffect(() => {
    notifyRef.current = notifyBrowser
  }, [notifyBrowser])

  const fetchAlerts = useCallback(() => api.alerts({ state: 'open', unread: true, limit: 30 }), [])
  const { data, refresh } = usePolling(fetchAlerts, 15000)
  const refreshRef = useRef(refresh)
  useEffect(() => {
    refreshRef.current = refresh
  }, [refresh])

  useEffect(() => {
    let socket
    let retry
    let delay = 1000
    let closed = false

    const showBrowserNotification = (alert) => {
      if (!notifyRef.current || !browserNotificationsSupported() || Notification.permission !== 'granted') return
      if (document.hasFocus()) return // you're looking at the dashboard already
      const label = ALERT_TYPES[alert.type]?.label ?? alert.type
      const note = new Notification(`${label} — ${alert.camera_name ?? alert.camera_id}`, {
        body: alert.message,
        tag: `alert-${alert.id}`,
      })
      note.onclick = () => {
        window.focus()
        note.close()
      }
    }

    const connect = () => {
      const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
      socket = new WebSocket(`${scheme}://${window.location.host}/api/ws/alerts`)
      socket.onopen = () => {
        delay = 1000
        setConnection('live')
        refreshRef.current() // catch up on anything missed while disconnected
      }
      socket.onmessage = (event) => {
        let message
        try {
          message = JSON.parse(event.data)
        } catch {
          return
        }
        if (message.type === 'alert_created') {
          setToasts((current) => [...current.filter((a) => a.id !== message.alert.id), message.alert])
          showBrowserNotification(message.alert)
          refreshRef.current()
        } else if (message.type === 'alert_updated') {
          refreshRef.current()
        }
      }
      socket.onclose = () => {
        if (closed) return
        setConnection('reconnecting')
        retry = setTimeout(connect, delay)
        delay = Math.min(delay * 2, MAX_BACKOFF_MS)
      }
    }

    connect()
    return () => {
      closed = true
      clearTimeout(retry)
      socket?.close()
    }
  }, [])

  const dismissToast = useCallback((id) => setToasts((current) => current.filter((a) => a.id !== id)), [])

  const setBrowserNotifications = useCallback(async (enabled) => {
    if (!browserNotificationsSupported()) return 'unsupported'
    if (enabled && Notification.permission !== 'granted') {
      const result = await Notification.requestPermission() // must be called from a click
      if (result !== 'granted') {
        setNotifyBrowser(false)
        return result
      }
    }
    try {
      localStorage.setItem(NOTIFY_KEY, enabled ? '1' : '0')
    } catch {
      /* preference just won't persist */
    }
    setNotifyBrowser(enabled)
    return 'granted'
  }, [])

  const value = useMemo(
    () => ({
      alerts: data?.items ?? [],
      unread: data?.unread ?? 0,
      open: data?.open ?? 0,
      refresh,
      toasts,
      dismissToast,
      connection,
      notifyBrowser,
      setBrowserNotifications,
      browserNotificationsSupported: browserNotificationsSupported(),
    }),
    [data, refresh, toasts, dismissToast, connection, notifyBrowser, setBrowserNotifications],
  )
  return <AlertsContext.Provider value={value}>{children}</AlertsContext.Provider>
}
