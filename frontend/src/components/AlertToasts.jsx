import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { X } from 'lucide-react'
import { alertSnapshotUrl, api } from '../api'
import { useAlerts } from '../hooks/useAlerts'
import { ALERT_TYPES, SEVERITIES } from '../utils/meta'
import AlertIcon from './AlertIcon'
import { Button } from './ui'

const TOAST_SECONDS = 15

function Toast({ alert, onDismiss, onRead, onView }) {
  useEffect(() => {
    const id = setTimeout(onDismiss, TOAST_SECONDS * 1000)
    return () => clearTimeout(id)
  }, [onDismiss])

  const critical = alert.severity === 'critical' || alert.severity === 'high'
  const meta = ALERT_TYPES[alert.type]
  return (
    <div
      role="alert"
      className={`pointer-events-auto w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border bg-slate-900 shadow-2xl ${
        critical ? 'border-red-500/50 shadow-red-950/40' : 'border-amber-500/40 shadow-amber-950/30'
      }`}
    >
      <div className="flex gap-3 p-3">
        {alert.has_snapshot ? (
          <img src={alertSnapshotUrl(alert.id)} alt="" className="h-16 w-16 shrink-0 rounded-lg object-cover" />
        ) : (
          <span
            className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-lg ${critical ? 'bg-red-500/15 text-red-400' : 'bg-amber-500/15 text-amber-400'}`}
          >
            <AlertIcon name={meta?.icon} className="h-7 w-7" />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p className="flex items-start justify-between gap-2 text-sm font-semibold">
            <span className={critical ? 'text-red-300' : 'text-amber-300'}>{meta?.label ?? alert.type}</span>
            <button onClick={onDismiss} aria-label="Dismiss" className="text-slate-500 hover:text-slate-200">
              <X className="h-4 w-4" />
            </button>
          </p>
          <p className="truncate text-xs text-slate-300">{alert.message}</p>
          <p className="truncate text-xs text-slate-500">
            {alert.camera_name} · {SEVERITIES[alert.severity]?.label}
          </p>
          <div className="mt-2 flex gap-2">
            <Button variant={critical ? 'danger' : 'primary'} className="px-2 py-1 text-xs" onClick={onView}>
              View
            </Button>
            <Button className="px-2 py-1 text-xs" onClick={onRead}>
              Mark read
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function AlertToasts() {
  const { toasts, dismissToast, refresh } = useAlerts()
  const navigate = useNavigate()

  const markRead = async (alert) => {
    dismissToast(alert.id)
    try {
      await api.readAlert(alert.id)
    } finally {
      refresh()
    }
  }

  return (
    <div className="pointer-events-none fixed right-4 top-16 z-[60] flex flex-col gap-3">
      {toasts.slice(-3).map((alert) => (
        <Toast
          key={alert.id}
          alert={alert}
          onDismiss={() => dismissToast(alert.id)}
          onRead={() => markRead(alert)}
          onView={() => {
            dismissToast(alert.id)
            navigate('/alerts')
          }}
        />
      ))}
    </div>
  )
}
