// Display metadata for alert and event types, shared by every page.
export const ALERT_TYPES = {
  unknown_person: { label: 'Unknown person', icon: 'ShieldAlert' },
  restricted_area: { label: 'Restricted area', icon: 'OctagonAlert' },
  suspicious_activity: { label: 'Suspicious activity', icon: 'Eye' },
  camera_offline: { label: 'Camera offline', icon: 'VideoOff' },
}

export const SEVERITIES = {
  critical: { label: 'Critical', tone: 'red' },
  high: { label: 'High', tone: 'red' },
  medium: { label: 'Medium', tone: 'amber' },
  low: { label: 'Low', tone: 'blue' },
}

// Event types, least to most serious. An event takes the most serious thing seen in it.
export const EVENT_TYPES = {
  motion: { label: 'Motion', tone: 'slate' },
  person: { label: 'Person', tone: 'blue' },
  suspicious_activity: { label: 'Suspicious', tone: 'amber' },
  unknown_person: { label: 'Unknown person', tone: 'red' },
  restricted_area: { label: 'Restricted area', tone: 'red' },
}

export const eventLabel = (type) => EVENT_TYPES[type]?.label ?? type

// The explainable rules behind restricted-area and suspicious-activity alerts.
// Each one is a plain condition, never a judgement of intent.
export const RULES = {
  zone_intrusion: { label: 'Zone intrusion', help: 'A person entered a restricted zone.' },
  loitering: { label: 'Loitering in zone', help: 'A person stayed inside a restricted zone longer than its limit.' },
  repeated_entry: { label: 'Repeated entry', help: 'A restricted zone was entered several times within a short period.' },
  after_hours: { label: 'Security hours', help: "A person was seen during this camera's security hours." },
  fall_like: { label: 'Fall-like movement', help: 'A person went from upright to lying quickly and stayed down. Estimated from their outline only, so it can be wrong.' },
  lingering: { label: 'Lingering in view', help: 'One person has been in view for a long time.' },
}

export const ruleLabel = (rule) => RULES[rule]?.label ?? null
