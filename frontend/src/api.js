// Thin fetch wrapper. A 401 anywhere sends the app back to the login screen.

let onUnauthorized = () => {}

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler
}

export const tzOffsetMinutes = () => -new Date().getTimezoneOffset()

export function buildQuery(params) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, v)
  }
  const s = qs.toString()
  return s ? `?${s}` : ''
}

export async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401 && path !== '/login') {
    onUnauthorized()
    throw new Error('Not logged in')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
  return data
}
