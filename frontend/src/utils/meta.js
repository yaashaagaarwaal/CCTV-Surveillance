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
