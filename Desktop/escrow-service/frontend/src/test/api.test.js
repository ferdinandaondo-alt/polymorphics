import { describe, expect, it, vi } from 'vitest'
import { ApiError, api, formatDetail, hasToken, setToken } from '../api'

const respond = (status, body) => vi.fn(async () => ({ ok: status < 400, status, statusText: 'x', json: async () => body }))

describe('api client', () => {
  it('formats FastAPI validation errors readably', () => {
    expect(formatDetail('Only the buyer can do this')).toBe('Only the buyer can do this')
    expect(formatDetail([{ loc: ['body', 'amount'], msg: 'Input should be greater than 0' }])).toBe('amount: Input should be greater than 0')
    expect(formatDetail(null)).toBeNull()
  })
  it('throws ApiError carrying status and the server message', async () => {
    globalThis.fetch = respond(409, { detail: 'Cannot move a transaction from funded to funded' })
    await expect(api.post('/x')).rejects.toMatchObject({ status: 409, message: 'Cannot move a transaction from funded to funded' })
  })
  it('sends the bearer token and JSON body', async () => {
    setToken('abc')
    globalThis.fetch = respond(200, {})
    await api.post('/transactions', { a: 1 })
    const [url, opts] = globalThis.fetch.mock.calls[0]
    expect(url).toBe('/api/transactions')
    expect(opts.headers.Authorization).toBe('Bearer abc')
    expect(JSON.parse(opts.body)).toEqual({ a: 1 })
    setToken(null)
  })
  it('logs the user out when a token is rejected (expired or account frozen)', async () => {
    setToken('stale')
    const onLogout = vi.fn()
    window.addEventListener('auth:logout', onLogout)
    globalThis.fetch = respond(401, { detail: 'Invalid or expired token' })
    await expect(api.get('/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(hasToken()).toBe(false)
    expect(onLogout).toHaveBeenCalledTimes(1)
    window.removeEventListener('auth:logout', onLogout)
  })
  it('does NOT trigger logout for a wrong password (no token yet)', async () => {
    setToken(null)
    const onLogout = vi.fn()
    window.addEventListener('auth:logout', onLogout)
    globalThis.fetch = respond(401, { detail: 'Invalid email or password' })
    await expect(api.post('/auth/login', {})).rejects.toMatchObject({ message: 'Invalid email or password' })
    expect(onLogout).not.toHaveBeenCalled()
    window.removeEventListener('auth:logout', onLogout)
  })
  it('gives a friendly message when the server is unreachable', async () => {
    globalThis.fetch = vi.fn(async () => { throw new TypeError('Failed to fetch') })
    await expect(api.get('/x')).rejects.toMatchObject({ status: 0, message: expect.stringContaining('Could not reach the server') })
  })
})
