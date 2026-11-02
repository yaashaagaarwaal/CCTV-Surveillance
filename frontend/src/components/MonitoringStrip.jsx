import { Link } from 'react-router-dom'
import { Badge } from './ui'

/**
 * What a camera is watching for right now, under its picture: restricted zones (red while someone is inside),
 * security hours, the crowd limit and the experimental fall check. When nothing is set it says so, because
 * without a rule the camera only records and detects: it cannot alert on a zone, hours or a crowd.
 */
export default function MonitoringStrip({ monitoring }) {
  if (!monitoring) return null
  const { zones = [], security_hours: hours, crowd, fall_check: fall, lingering, fire } = monitoring
  const chips = []

  zones.forEach((zone) =>
    chips.push(
      <Badge key={`zone-${zone.id}`} tone={zone.occupied ? 'red' : zone.active ? 'amber' : 'slate'} title={zone.active ? 'Restricted zone: a person standing inside raises an alert' : 'Restricted zone, outside its scheduled hours so not enforced right now'}>
        Zone: {zone.name}
        {zone.occupied ? ' · someone inside' : zone.active ? '' : ' · off-hours'}
      </Badge>,
    ),
  )
  if (hours) {
    chips.push(
      <Badge key="hours" tone={hours.active_now ? 'red' : 'slate'} title="A person seen during these hours raises an alert (the server's local time)">
        Security hours {hours.start}–{hours.end}
        {hours.active_now ? ' · active now' : ''}
      </Badge>,
    )
  }
  if (crowd?.threshold > 0) {
    chips.push(
      <Badge key="crowd" tone={crowd.over ? 'red' : 'blue'} title="Alert when at least this many people stay in view. A standard detector misses overlapping people, so the real number can be higher.">
        Crowd: {crowd.count}
        {crowd.approximate ? '+' : ''} of {crowd.threshold}
        {crowd.region ? ` in ${crowd.region}` : ''}
        {crowd.over ? ` · ${crowd.over_seconds}s of ${crowd.seconds}s` : ''}
      </Badge>,
    )
  }
  if (fall) {
    chips.push(
      <Badge key="fall" tone="amber" title="Experimental, from the person's outline only. Every alert needs a person to review the recording.">
        Fall check (experimental)
      </Badge>,
    )
  }
  if (lingering) {
    chips.push(
      <Badge key="linger" tone="slate" title="Alert when one person stays in view for a long time anywhere">
        Lingering check
      </Badge>,
    )
  }

  // Fire and smoke need no setup (server-wide); null means the feature is off (no weights, or FIRE__ENABLED=false).
  const fireOn = fire && (fire.fire || fire.smoke)
  const fireActive = fireOn && (fire.fire.active || fire.smoke.active)

  return (
    <div className="flex flex-wrap items-center gap-1 border-t border-white/[0.06] bg-black/50 px-2 py-1.5 text-[11px]" aria-label="Active monitoring rules">
      {chips.length ? (
        chips
      ) : (
        <span className="text-slate-500">
          No rules set: this camera records and detects people but cannot alert on a zone, hours or crowd.{' '}
          <Link to="/cameras" className="text-sky-400 hover:underline">
            Set them up
          </Link>
        </span>
      )}
      {fireOn && (
        <Badge tone={fireActive ? 'red' : 'slate'} title="An AI model watches for flames and smoke. It needs several checks in a row before it alerts; lamps, sunsets, steam or fog can fool it.">
          Fire &amp; smoke check{fireActive ? ' · detected' : ''}
        </Badge>
      )}
    </div>
  )
}
