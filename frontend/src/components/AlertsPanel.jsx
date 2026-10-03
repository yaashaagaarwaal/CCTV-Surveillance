import { Link } from 'react-router-dom'
import { Check, CheckCheck, ShieldCheck, TriangleAlert, User } from 'lucide-react'
import { alertSnapshotUrl, api } from '../api'
import { useAlerts } from '../hooks/useAlerts'
import { ALERT_TYPES, SEVERITIES } from '../utils/meta'
import { percent, timeAgo } from '../utils/format'
import AlertIcon from './AlertIcon'
import { Badge, Button, Card } from './ui'

/**
 * Unread open alerts (stored in the database, pushed live) plus live
 * conditions that exist right now (a person in view). The first stay until
 * someone marks them read or resolves them; the second disappear on their own.
 */
export default function AlertsPanel({ liveAlerts, nameOf }) {
  const { alerts, unread, refresh, connection } = useAlerts()
  const live = liveAlerts ?? []
  const total = unread + live.length

  const act = (action) => async () => {
    try {
      await action()
    } finally {
      refresh()
    }
  }

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <TriangleAlert className="h-4 w-4 text-slate-400" />
          Active alerts
          <span
            title={connection === 'live' ? 'Receiving alerts in real time' : 'Reconnecting — alerts refresh every 15 s meanwhile'}
            className={`flex items-center gap-1 rounded px-1.5 text-[10px] font-semibold ${connection === 'live' ? 'text-emerald-400' : 'text-amber-400'}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${connection === 'live' ? 'bg-emerald-400' : 'bg-amber-400'}`} />
            {connection === 'live' ? 'LIVE' : 'RETRYING'}
          </span>
        </h2>
        <div className="flex items-center gap-2">
          {unread > 1 && (
            <button onClick={act(api.readAllAlerts)} className="flex items-center gap-1 text-xs text-sky-400 hover:underline">
              <CheckCheck className="h-3 w-3" /> Mark all read
            </button>
          )}
          <Badge tone={total ? 'red' : 'green'}>{total}</Badge>
        </div>
      </div>

      {total === 0 ? (
        <div className="flex items-center gap-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-sm text-emerald-300">
          <ShieldCheck className="h-5 w-5 shrink-0" />
          All clear — no active alerts
        </div>
      ) : (
        <ul className="space-y-2">
          {alerts.slice(0, 5).map((alert) => {
            const severe = alert.severity === 'high' || alert.severity === 'critical'
            return (
              <li
                key={alert.id}
                className={`flex items-start gap-3 rounded-lg border p-3 ${severe ? 'border-red-500/40 bg-red-500/10' : 'border-amber-500/30 bg-amber-500/10'}`}
              >
                {alert.has_snapshot ? (
                  <img src={alertSnapshotUrl(alert.id)} alt="" className="h-12 w-12 shrink-0 rounded-md object-cover" />
                ) : (
                  <AlertIcon name={ALERT_TYPES[alert.type]?.icon} className={`mt-0.5 h-4 w-4 shrink-0 ${severe ? 'text-red-400' : 'text-amber-400'}`} />
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{ALERT_TYPES[alert.type]?.label ?? alert.type}</p>
                  <p className="truncate text-xs text-slate-400">
                    {nameOf(alert.camera_id)} · {timeAgo(alert.created_at)}
                    {alert.occurrences > 1 && ` · ×${alert.occurrences}`}
                  </p>
                  <p className="truncate text-xs text-slate-500">{alert.message}</p>
                  <div className="mt-1.5 flex gap-1.5">
                    <Button className="px-2 py-0.5 text-xs" onClick={act(() => api.readAlert(alert.id))}>
                      <Check className="h-3 w-3" /> Read
                    </Button>
                    <Button className="px-2 py-0.5 text-xs" onClick={act(() => api.resolveAlert(alert.id))}>
                      Resolve
                    </Button>
                  </div>
                </div>
                <Badge tone={SEVERITIES[alert.severity]?.tone}>{SEVERITIES[alert.severity]?.label.toUpperCase()}</Badge>
              </li>
            )
          })}
          {unread > 5 && (
            <li className="text-center">
              <Link to="/alerts" className="text-xs text-sky-400 hover:underline">
                +{unread - 5} more unread alerts
              </Link>
            </li>
          )}
          {live.map((alert) => (
            <li key={alert.id} className="flex items-start gap-3 rounded-lg border border-sky-500/30 bg-sky-500/10 p-3">
              <User className="mt-0.5 h-4 w-4 shrink-0 text-sky-400" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{alert.message}</p>
                <p className="truncate text-xs text-slate-400">
                  {alert.camera_name}
                  {alert.confidence != null && ` · ${percent(alert.confidence)} confidence`}
                </p>
              </div>
              <Badge tone="blue">LIVE</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
