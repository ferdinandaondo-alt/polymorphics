// Thin wrapper around fetch. Every call goes to /api/... (proxied to the backend).
const BASE = import.meta.env.VITE_API_BASE || '/api'
const KEY = 'escrow_token'

let token = null
try { token = localStorage.getItem(KEY) } catch { /* storage unavailable */ }

export function setToken(t) {
  token = t
  try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY) } catch { /* ignore */ }
}
export const hasToken = () => Boolean(token)

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

// FastAPI returns either a string or a list of {loc, msg} for validation errors.
export function formatDetail(detail) {
  if (!detail) return null
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== 'body').join('.') : ''
      return field ? `${field}: ${d.msg}` : d.msg
    }).join('; ')
  }
  return 'Something went wrong'
}

async function request(method, path, body) {
  let res
  try {
    res = await fetch(BASE + path, {
      method,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Could not reach the server. Check your connection and try again.')
  }
  let data = null
  try { data = await res.json() } catch { /* empty body */ }
  if (res.status === 401 && token) {          // token expired, or the account was frozen
    setToken(null)
    window.dispatchEvent(new Event('auth:logout'))
  }
  if (!res.ok) throw new ApiError(res.status, formatDetail(data?.detail) || res.statusText || 'Request failed')
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, body = {}) => request('POST', p, body),
}
