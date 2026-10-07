// Thin wrapper around fetch for the backend API. Every failure becomes an
// Error with a human-readable message (the backend's `detail` when present).
async function request(path, { method = 'GET', body, form, anonymous = false } = {}) {
  let res
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      // `form` (FormData) is sent as multipart; the browser sets its own headers.
      body: form ?? (body ? JSON.stringify(body) : undefined),
    })
  } catch {
    throw new Error('Cannot reach the backend')
  }

  if (res.status === 401 && !anonymous) {
    // Session expired or logged out elsewhere: let the app show the login page.
    window.dispatchEvent(new Event('auth:unauthorized'))
  }

  if (!res.ok) {
    // 502-504 come from the dev proxy when the backend isn't running.
    let message = res.status >= 502 && res.status <= 504 ? 'Cannot reach the backend' : `Request failed (${res.status})`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
      else if (Array.isArray(data.detail)) message = data.detail.map((d) => d.msg).join(', ')
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    throw new Error(message)
  }
  return res.status === 204 ? null : res.json()
}

// false is a real value for booleans like `acknowledged`; only drop unset ones.
function query(params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, value)
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const api = {
  health: () => request('/health', { anonymous: true }),
  me: () => request('/auth/me', { anonymous: true }),
  login: (username, password) => request('/auth/login', { method: 'POST', body: { username, password }, anonymous: true }),
  logout: () => request('/auth/logout', { method: 'POST', anonymous: true }),
  changePassword: (current_password, new_password) =>
    request('/auth/change-password', { method: 'POST', body: { current_password, new_password } }),
  users: () => request('/users'),
  createUser: (body) => request('/users', { method: 'POST', body }),
  updateUser: (id, body) => request(`/users/${id}`, { method: 'PATCH', body }),
  deleteUser: (id) => request(`/users/${id}`, { method: 'DELETE' }),
  zones: (cameraId) => request(`/cameras/${cameraId}/zones`),
  createZone: (cameraId, body) => request(`/cameras/${cameraId}/zones`, { method: 'POST', body }),
  updateZone: (id, body) => request(`/zones/${id}`, { method: 'PATCH', body }),
  deleteZone: (id) => request(`/zones/${id}`, { method: 'DELETE' }),
  rules: (cameraId) => request(`/cameras/${cameraId}/rules`),
  setRules: (cameraId, body) => request(`/cameras/${cameraId}/rules`, { method: 'PUT', body }),
  notificationStatus: () => request('/notifications/status'),
  sendTestEmail: () => request('/notifications/test-email', { method: 'POST' }),
  summary: () => request('/dashboard/summary'),
  cameras: () => request('/cameras'),
  createCamera: (body) => request('/cameras', { method: 'POST', body }),
  updateCamera: (id, body) => request(`/cameras/${id}`, { method: 'PATCH', body }),
  deleteCamera: (id) => request(`/cameras/${id}`, { method: 'DELETE' }),
  testCamera: (body) => request('/cameras/test', { method: 'POST', body }),
  videoFiles: () => request('/sources/files'),
  people: () => request('/people'),
  recognitionStatus: () => request('/people/status'),
  createPerson: (name) => request('/people', { method: 'POST', body: { name } }),
  renamePerson: (id, name) => request(`/people/${id}`, { method: 'PATCH', body: { name } }),
  deletePerson: (id) => request(`/people/${id}`, { method: 'DELETE' }),
  addFacePhotos: (id, files) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    return request(`/people/${id}/faces`, { method: 'POST', form })
  },
  addFaceFromCamera: (id, cameraId) =>
    request(`/people/${id}/faces/from-camera`, { method: 'POST', body: { camera_id: cameraId } }),
  deleteFaceSample: (personId, sampleId) => request(`/people/${personId}/faces/${sampleId}`, { method: 'DELETE' }),
  alerts: (params = {}) => request(`/alerts${query(params)}`),
  readAlert: (id) => request(`/alerts/${id}/read`, { method: 'POST' }),
  readAllAlerts: () => request('/alerts/read-all', { method: 'POST' }),
  resolveAlert: (id) => request(`/alerts/${id}/resolve`, { method: 'POST' }),
  deleteAlert: (id) => request(`/alerts/${id}`, { method: 'DELETE' }),
  event: (id) => request(`/events/${id}`),
  events: (params = {}) => request(`/events${query(params)}`),
  deleteEvent: (id) => request(`/events/${id}`, { method: 'DELETE' }),
}

export const streamUrl = (cameraId) => `/api/cameras/${cameraId}/stream`
export const snapshotUrl = (cameraId) => `/api/cameras/${cameraId}/snapshot`
export const videoUrl = (eventId) => `/api/events/${eventId}/video`
export const downloadUrl = (eventId) => `/api/events/${eventId}/download`
export const thumbnailUrl = (eventId) => `/api/events/${eventId}/thumbnail`
export const faceImageUrl = (personId, sampleId) => `/api/people/${personId}/faces/${sampleId}/image`
export const alertSnapshotUrl = (alertId) => `/api/alerts/${alertId}/snapshot`
