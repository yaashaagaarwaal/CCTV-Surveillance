import { useState } from 'react'
import { Bell, BellRing, Check, CheckCheck, CircleCheck, Film, Mail, Trash2 } from 'lucide-react'
import { alertSnapshotUrl, api } from '../api'
import AlertIcon from '../components/AlertIcon'
import Pagination from '../components/Pagination'
import VideoModal from '../components/VideoModal'
import { Badge, Button, Card, EmptyState, ErrorBanner, Modal, Spinner, inputClass } from '../components/ui'
import { useAlerts } from '../hooks/useAlerts'
import { useAuth } from '../hooks/useAuth'
import { useCameras } from '../hooks/useCameras'
import { usePolling } from '../hooks/usePolling'
import { formatDateTime, timeAgo } from '../utils/format'
import { ALERT_TYPES, RULES, SEVERITIES } from '../utils/meta'

const PAGE_SIZE = 12

// "Why": which rule fired, the zone it applied to, and how sure the person detector was.
function Why({ alert }) {
  const d = alert.details ?? {}
  const rule = RULES[d.rule]
  if (!rule && !d.zone) return null
  return (
    <p className="text-xs text-slate-400" title={rule?.help}>
      {rule && <span className="font-medium text-slate-300">{rule.label}</span>}
      {d.zone && <span>{rule ? ' · ' : ''}Zone: {d.zone}</span>}
      {d.confidence != null && <span> · person detection {Math.round(d.confidence * 100)}%</span>}
      {d.rule === 'fall_like' && <span className="text-amber-300"> · estimate from outline only, can be wrong</span>}
    </p>
  )
}

function AlertCard({ alert, cameraName, canDelete, onRead, onResolve, onDelete, onSnapshot, onPlay }) {
  const meta = ALERT_TYPES[alert.type]
  const severity = SEVERITIES[alert.severity]
  return (
    <Card className={`flex gap-4 p-3 sm:p-4 ${alert.resolved ? 'opacity-60' : !alert.read ? 'border-red-500/40' : ''}`}>
      <button
        onClick={() => onSnapshot(alert)}
        disabled={!alert.has_snapshot}
        className="flex h-24 w-32 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-slate-950 text-slate-700 sm:h-28 sm:w-40"
        aria-label="Enlarge snapshot"
      >
        {alert.has_snapshot ? (
          <img src={alertSnapshotUrl(alert.id)} alt="Snapshot" loading="lazy" className="h-full w-full object-cover" />
        ) : (
          <AlertIcon name={meta?.icon} className="h-8 w-8" />
        )}
      </button>

      <div className="flex min-w-0 flex-1 flex-col justify-between gap-2">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            {!alert.read && <span className="h-2 w-2 rounded-full bg-sky-400" title="Unread" />}
            <p className="flex items-center gap-1.5 font-semibold">
              <AlertIcon name={meta?.icon} className="h-4 w-4 text-slate-400" />
              {meta?.label ?? alert.type}
            </p>
            <Badge tone={severity?.tone}>{severity?.label.toUpperCase()}</Badge>
            {alert.resolved && (
              <Badge tone="green">
                <CircleCheck className="h-3 w-3" /> Resolved{alert.resolved_by === 'system' ? ' automatically' : ` by ${alert.resolved_by}`}
              </Badge>
            )}
            {alert.occurrences > 1 && <Badge>×{alert.occurrences}</Badge>}
          </div>
          <p className="text-sm text-slate-300">{alert.message}</p>
          <Why alert={alert} />
          <p className="truncate text-xs text-slate-400">{cameraName}</p>
          <p className="text-xs text-slate-500">
            {formatDateTime(alert.created_at)} · {timeAgo(alert.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {!alert.read && (
            <Button className="px-2.5 py-1 text-xs" onClick={() => onRead(alert)}>
              <Check className="h-3.5 w-3.5" /> Mark read
            </Button>
          )}
          {!alert.resolved && (
            <Button variant="primary" className="px-2.5 py-1 text-xs" onClick={() => onResolve(alert)}>
              <CircleCheck className="h-3.5 w-3.5" /> Resolve
            </Button>
          )}
          {alert.event_available && (
            <Button className="px-2.5 py-1 text-xs" onClick={() => onPlay(alert)}>
              <Film className="h-3.5 w-3.5" /> Recording
            </Button>
          )}
          {canDelete && (
            <Button variant="ghost" className="px-2.5 py-1 text-xs text-slate-400 hover:text-red-400" onClick={() => onDelete(alert)} aria-label="Delete alert">
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>
    </Card>
  )
}

function NotificationSettings() {
  const { isAdmin } = useAuth()
  const { notifyBrowser, setBrowserNotifications, browserNotificationsSupported } = useAlerts()
  const status = usePolling(api.notificationStatus, 30000)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const email = status.data?.email

  const toggleBrowser = async () => {
    const result = await setBrowserNotifications(!notifyBrowser)
    if (result === 'denied') setMessage({ ok: false, text: 'Notifications are blocked for this site in your browser settings.' })
    else if (result === 'unsupported') setMessage({ ok: false, text: 'This browser does not support notifications.' })
    else setMessage(null)
  }

  const testEmail = async () => {
    setBusy(true)
    setMessage(null)
    try {
      const result = await api.sendTestEmail()
      setMessage({ ok: true, text: `Test email sent to ${result.recipients} recipient(s).` })
    } catch (err) {
      setMessage({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="grid gap-4 p-4 sm:grid-cols-2">
      <div className="space-y-2">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <BellRing className="h-4 w-4 text-slate-400" /> Browser notifications
        </p>
        <p className="text-xs text-slate-500">A desktop pop-up when an alert arrives while this tab is in the background (the page must stay open).</p>
        <Button onClick={toggleBrowser} disabled={!browserNotificationsSupported}>
          {notifyBrowser ? 'Turn off' : 'Turn on'}
        </Button>
        {notifyBrowser && <Badge tone="green">On</Badge>}
      </div>
      <div className="space-y-2">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Mail className="h-4 w-4 text-slate-400" /> Email notifications
        </p>
        {email?.active ? (
          <>
            <p className="text-xs text-slate-500">
              Sending alerts of <span className="text-slate-300">{email.min_severity}</span> severity or higher to {email.recipients} recipient(s).
            </p>
            {isAdmin && (
              <Button onClick={testEmail} disabled={busy}>
                {busy && <Spinner className="h-4 w-4" />} Send test email
              </Button>
            )}
          </>
        ) : (
          <p className="text-xs text-slate-500">
            Off. Email is configured on the server with environment variables (see <code>backend/.env.example</code>).
          </p>
        )}
      </div>
      {message && <div className={`sm:col-span-2 text-xs ${message.ok ? 'text-emerald-400' : 'text-red-400'}`}>{message.text}</div>}
    </Card>
  )
}

export default function AlertsPage() {
  const { isAdmin } = useAuth()
  const { nameOf } = useCameras()
  const { refresh: refreshShared } = useAlerts()
  const [filters, setFilters] = useState({ state: 'open', type: '', severity: '', unread: false })
  const [page, setPage] = useState(0)
  const [snapshot, setSnapshot] = useState(null)
  const [playing, setPlaying] = useState(null)
  const [actionError, setActionError] = useState(null)

  const { data, error, loading, refresh } = usePolling(
    () =>
      api.alerts({
        state: filters.state,
        type: filters.type,
        severity: filters.severity,
        unread: filters.unread ? true : undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    5000,
    [filters.state, filters.type, filters.severity, filters.unread, page],
  )
  const items = data?.items ?? []
  const setFilter = (key, value) => {
    setFilters((f) => ({ ...f, [key]: value }))
    setPage(0)
  }

  const run = async (action) => {
    setActionError(null)
    try {
      await action()
    } catch (err) {
      setActionError(err.message)
    } finally {
      refresh()
      refreshShared()
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Alerts</h1>
          <p className="text-sm text-slate-500">
            {data ? `${data.open} open · ${data.unread} unread` : 'Unknown people, restricted areas, suspicious activity and camera outages'}
          </p>
        </div>
        <Button onClick={() => run(api.readAllAlerts)} disabled={!data?.unread}>
          <CheckCheck className="h-4 w-4" /> Mark all read
        </Button>
      </div>

      <NotificationSettings />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <select className={inputClass} value={filters.state} onChange={(e) => setFilter('state', e.target.value)} aria-label="Filter by state">
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
          <option value="all">All</option>
        </select>
        <select className={inputClass} value={filters.type} onChange={(e) => setFilter('type', e.target.value)} aria-label="Filter by type">
          <option value="">All types</option>
          {Object.entries(ALERT_TYPES).map(([value, meta]) => (
            <option key={value} value={value}>
              {meta.label}
            </option>
          ))}
        </select>
        <select className={inputClass} value={filters.severity} onChange={(e) => setFilter('severity', e.target.value)} aria-label="Filter by severity">
          <option value="">Any severity</option>
          {Object.entries(SEVERITIES).map(([value, meta]) => (
            <option key={value} value={value}>
              {meta.label}
            </option>
          ))}
        </select>
        <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300">
          <input type="checkbox" checked={filters.unread} onChange={(e) => setFilter('unread', e.target.checked)} className="h-4 w-4 accent-sky-500" />
          Unread only
        </label>
      </div>

      <ErrorBanner>{error || actionError}</ErrorBanner>

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner className="h-8 w-8" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState icon={Bell} title="No alerts here">
          Alerts are created for unknown people, people in restricted areas, suspicious activity and cameras that stay offline.
        </EmptyState>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {items.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              cameraName={nameOf(alert.camera_id)}
              canDelete={isAdmin}
              onRead={(a) => run(() => api.readAlert(a.id))}
              onResolve={(a) => run(() => api.resolveAlert(a.id))}
              onDelete={(a) => run(() => api.deleteAlert(a.id))}
              onSnapshot={setSnapshot}
              onPlay={(a) => run(async () => setPlaying(await api.event(a.event_id)))}
            />
          ))}
        </div>
      )}

      <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onChange={setPage} />

      {snapshot && (
        <Modal title={`${nameOf(snapshot.camera_id)} — ${formatDateTime(snapshot.created_at)}`} onClose={() => setSnapshot(null)} wide>
          <img src={alertSnapshotUrl(snapshot.id)} alt="Alert snapshot" className="w-full rounded-lg" />
        </Modal>
      )}
      {playing && <VideoModal event={playing} cameraName={nameOf(playing.camera_id)} onClose={() => setPlaying(null)} />}
    </div>
  )
}
