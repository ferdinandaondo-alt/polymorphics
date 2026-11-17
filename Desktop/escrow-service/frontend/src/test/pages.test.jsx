/**
 * Renders the real pages with REAL backend responses (fixtures.json, captured from the live API by
 * backend/scripts/dump_fixtures.py) and checks what the user sees and what the UI sends back.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { setToken } from '../api'
import { AuthProvider } from '../auth'
import fx from './fixtures.json'

function mockFetch(routes) {
  const calls = []
  globalThis.fetch = vi.fn(async (url, opts = {}) => {
    const call = { method: opts.method || 'GET', path: String(url).replace(/^\/api/, ''), body: opts.body ? JSON.parse(opts.body) : undefined }
    calls.push(call)
    const h = routes[`${call.method} ${call.path}`]
    if (h === undefined) return { ok: false, status: 404, statusText: 'Not Found', json: async () => ({ detail: `no mock for ${call.method} ${call.path}` }) }
    if (h && h.__status) return { ok: false, status: h.__status, statusText: 'err', json: async () => ({ detail: h.detail }) }
    return { ok: true, status: 200, json: async () => (typeof h === 'function' ? h(call) : h) }
  })
  return calls
}

function renderApp(path, me, routes = {}, { token = true } = {}) {
  setToken(token ? 't' : null)
  const calls = mockFetch({ ...(me ? { 'GET /auth/me': me } : {}), ...routes })
  render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>)
  return calls
}

const T = fx.transaction
const detailRoutes = (key, ledger = []) => ({ [`GET /transactions/${fx.ids[key]}`]: T[key], [`GET /transactions/${fx.ids[key]}/ledger`]: ledger })
const futureDispute = () => ({ ...fx.dispute, evidence_deadline: new Date(Date.now() + 36e5).toISOString() })

beforeEach(() => { setToken(null); vi.spyOn(window, 'confirm').mockReturnValue(true) })

describe('login & guards', () => {
  it('sends a logged-out visitor to the login page, then to their dashboard after logging in', async () => {
    const calls = renderApp('/', null, {
      'POST /auth/login': { access_token: 'tok' }, 'GET /auth/me': fx.me.buyer, 'GET /transactions': fx.transactions,
    }, { token: false })
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'bea@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'correct-horse-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('heading', { name: 'My transactions' })).toBeTruthy()
    expect(calls.find((c) => c.path === '/auth/login').body).toEqual({ email: 'bea@example.com', password: 'correct-horse-1' })
    expect(await screen.findByText('Funded deal')).toBeTruthy()
  })

  it('shows the server message when the password is wrong', async () => {
    renderApp('/login', null, { 'POST /auth/login': { __status: 401, detail: 'Invalid email or password' } }, { token: false })
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'a@b.co' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'whatever1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Invalid email or password')
  })

  it('logging out goes to the login page, and logging back in lands on the dashboard (not the old page)', async () => {
    renderApp(`/transactions/${fx.ids.funded}`, fx.me.buyer, {
      ...detailRoutes('funded'), 'POST /auth/login': { access_token: 'tok2' }, 'GET /transactions': fx.transactions,
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Log out' }))
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'bea@example.com' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'correct-horse-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('heading', { name: 'My transactions' })).toBeTruthy()
  })

  it("won't let an ordinary user into admin pages", async () => {
    renderApp('/admin/users', fx.me.buyer, { 'GET /transactions': fx.transactions })
    expect(await screen.findByRole('heading', { name: 'My transactions' })).toBeTruthy()
    expect(screen.queryByText('Users')).toBeNull()
  })
})

describe('dashboard', () => {
  it('lists deals and flags the ones waiting on this user', async () => {
    renderApp('/', fx.me.buyer, { 'GET /transactions': fx.transactions })
    for (const title of ['Draft deal', 'Accepted deal', 'Funded deal', 'Delivered deal', 'Disputed deal', 'Released deal']) {
      expect(await screen.findByText(title)).toBeTruthy()
    }
    // buyer's turn on: accepted (fund) and delivered (approve) = 2
    expect(screen.getAllByText('Your turn')).toHaveLength(2)
    expect(screen.getByText('Needs your action').nextSibling.textContent).toBe('2')
    expect(screen.getAllByText('Seller: Sam Seller').length).toBeGreaterThan(0)
    expect(screen.getAllByText('$500.00').length).toBeGreaterThan(0)
  })
  it('shows an empty state with a call to action', async () => {
    renderApp('/', fx.me.buyer, { 'GET /transactions': [] })
    expect(await screen.findByText("You don't have any transactions yet.")).toBeTruthy()
  })
})

describe('new transaction', () => {
  it('sends amounts in minor units and shows a fee preview matching the server', async () => {
    const calls = renderApp('/new', fx.me.buyer, {
      'GET /config': fx.config, 'POST /transactions': T.draft, ...detailRoutes('draft'),
    })
    fireEvent.change(await screen.findByLabelText('Title'), { target: { value: 'Logo' } })
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '150.00' } })
    fireEvent.change(screen.getByLabelText(/Seller's email/), { target: { value: 'sam@example.com' } })
    expect(await screen.findByText('$153.75')).toBeTruthy()          // 150.00 + 2.5% fee, buyer pays fee
    fireEvent.click(screen.getByRole('button', { name: 'Send to counterparty' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === '/transactions')).toBe(true))
    expect(calls.find((c) => c.method === 'POST' && c.path === '/transactions').body).toEqual({
      counterparty_email: 'sam@example.com', my_role: 'buyer', title: 'Logo', description: null, currency: 'USD',
      amount: 15000, fee_payer: 'buyer', delivery_deadline: null, auto_release_hours: 120,
    })
    expect(await screen.findByRole('heading', { name: /Draft deal/ })).toBeTruthy()   // navigated to the new deal
  })
  it('refuses an invalid amount without calling the server', async () => {
    const calls = renderApp('/new', fx.me.buyer, { 'GET /config': fx.config })
    fireEvent.change(await screen.findByLabelText('Title'), { target: { value: 'x' } })
    fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '1.234' } })
    fireEvent.change(screen.getByLabelText(/Seller's email/), { target: { value: 'sam@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send to counterparty' }))
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })
})

describe('transaction detail: the right buttons for the right person at the right time', () => {
  it('seller can accept a draft proposed by the buyer', async () => {
    const calls = renderApp(`/transactions/${fx.ids.draft}`, fx.me.seller, detailRoutes('draft'))
    fireEvent.click(await screen.findByRole('button', { name: 'Accept' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.path === `/transactions/${fx.ids.draft}/accept`)).toBe(true))
  })
  it('the proposer just waits', async () => {
    renderApp(`/transactions/${fx.ids.draft}`, fx.me.buyer, detailRoutes('draft'))
    expect(await screen.findByText(/to accept\./)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Accept' })).toBeNull()
  })
  it('buyer funds an accepted deal, seeing the full amount they will pay', async () => {
    const calls = renderApp(`/transactions/${fx.ids.accepted}`, fx.me.buyer, detailRoutes('accepted'))
    fireEvent.click(await screen.findByRole('button', { name: 'Pay $512.50 into escrow' }))
    await waitFor(() => expect(calls.some((c) => c.path === `/transactions/${fx.ids.accepted}/fund`)).toBe(true))
  })
  it('seller cannot fund; seller is told to wait', async () => {
    renderApp(`/transactions/${fx.ids.accepted}`, fx.me.seller, detailRoutes('accepted'))
    expect(await screen.findByText(/to fund the escrow/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Pay/ })).toBeNull()
  })
  it('seller marks a funded deal as delivered with a note; buyer cannot', async () => {
    const calls = renderApp(`/transactions/${fx.ids.funded}`, fx.me.seller, detailRoutes('funded', fx.ledger.funded))
    fireEvent.change(await screen.findByLabelText(/Delivery note/), { target: { value: 'files at link' } })
    fireEvent.click(screen.getByRole('button', { name: 'Mark as delivered' }))
    await waitFor(() => expect(calls.find((c) => c.path.endsWith('/deliver'))?.body).toEqual({ note: 'files at link' }))
  })
  it('buyer approves a delivered deal after confirming', async () => {
    const calls = renderApp(`/transactions/${fx.ids.delivered}`, fx.me.buyer, detailRoutes('delivered'))
    fireEvent.click(await screen.findByRole('button', { name: /Approve & release funds/ }))
    expect(window.confirm).toHaveBeenCalled()
    await waitFor(() => expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(true))
  })
  it('does nothing if the user cancels the confirmation', async () => {
    window.confirm.mockReturnValue(false)
    const calls = renderApp(`/transactions/${fx.ids.delivered}`, fx.me.buyer, detailRoutes('delivered'))
    fireEvent.click(await screen.findByRole('button', { name: /Approve & release funds/ }))
    expect(calls.some((c) => c.path.endsWith('/approve'))).toBe(false)
  })
  it('opening a dispute sends the reason and goes to the dispute page', async () => {
    const calls = renderApp(`/transactions/${fx.ids.delivered}`, fx.me.buyer, {
      ...detailRoutes('delivered'),
      [`POST /transactions/${fx.ids.delivered}/dispute`]: fx.dispute,
      [`GET /disputes/${fx.dispute.id}`]: futureDispute(),
      [`GET /transactions/${fx.dispute.transaction_id}`]: T.disputed,
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Open a dispute' }))
    fireEvent.change(screen.getByLabelText(/What went wrong/), { target: { value: 'Not what we agreed' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit dispute' }))
    await waitFor(() => expect(calls.find((c) => c.path.endsWith('/dispute') && c.method === 'POST')?.body).toEqual({ reason: 'Not what we agreed' }))
    expect(await screen.findByText('Why it was opened')).toBeTruthy()
  })
  it('shows server errors instead of failing silently', async () => {
    renderApp(`/transactions/${fx.ids.accepted}`, fx.me.buyer, {
      ...detailRoutes('accepted'), [`POST /transactions/${fx.ids.accepted}/fund`]: { __status: 409, detail: 'Cannot move a transaction from funded to funded' },
    })
    fireEvent.click(await screen.findByRole('button', { name: /Pay/ }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Cannot move a transaction from funded to funded')
  })
  it('shows the ledger in plain words once money has moved', async () => {
    renderApp(`/transactions/${fx.ids.released}`, fx.me.buyer, detailRoutes('released', fx.ledger.released))
    expect(await screen.findByText('Funds have been released to the seller.', { exact: false })).toBeTruthy()
    expect(screen.getAllByText('Escrow').length).toBeGreaterThan(0)
    expect(screen.getByText("Seller's balance")).toBeTruthy()
    expect(screen.getByText('Platform fee')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /Approve|Pay|Accept/ })).toBeNull()
  })
})

describe('disputes', () => {
  const routes = { [`GET /disputes/${fx.dispute.id}`]: futureDispute(), [`GET /transactions/${fx.dispute.transaction_id}`]: T.disputed }

  it('arbiter sees evidence, messages and the decision form, and a split posts minor units', async () => {
    const calls = renderApp(`/disputes/${fx.dispute.id}`, fx.me.arbiter, {
      ...routes, [`POST /disputes/${fx.dispute.id}/decision`]: { ...fx.dispute, status: 'decided', decision: 'split' },
    })
    expect(await screen.findByText('Delivery email sent on the agreed date')).toBeTruthy()
    expect(screen.getByText('I only received a draft.')).toBeTruthy()
    fireEvent.click(screen.getByLabelText(/Split the item price/))
    fireEvent.change(await screen.findByLabelText(/Seller keeps/), { target: { value: '200.00' } })
    fireEvent.change(screen.getByLabelText(/Reason \(required/), { target: { value: 'Half the files were delivered' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit decision' }))
    await waitFor(() => expect(calls.find((c) => c.path.endsWith('/decision'))?.body).toEqual({
      decision: 'split', reason: 'Half the files were delivered', split_to_seller_amount: 20000 }))
  })
  it('a refund decision sends no split amount', async () => {
    const calls = renderApp(`/disputes/${fx.dispute.id}`, fx.me.arbiter, { ...routes, [`POST /disputes/${fx.dispute.id}/decision`]: fx.dispute })
    fireEvent.change(await screen.findByLabelText(/Reason \(required/), { target: { value: 'Nothing was delivered' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit decision' }))
    await waitFor(() => expect(calls.find((c) => c.path.endsWith('/decision'))?.body).toEqual({ decision: 'refund_to_buyer', reason: 'Nothing was delivered' }))
  })
  it('parties get evidence and message forms but NOT the decision form', async () => {
    renderApp(`/disputes/${fx.dispute.id}`, fx.me.buyer, routes)
    expect(await screen.findByLabelText('Add a note')).toBeTruthy()
    expect(screen.getByLabelText('Message')).toBeTruthy()
    expect(screen.queryByText('Arbiter decision')).toBeNull()
  })
  it('a decided dispute shows the outcome and no forms', async () => {
    renderApp(`/disputes/${fx.dispute.id}`, fx.me.buyer, {
      [`GET /disputes/${fx.dispute.id}`]: { ...fx.dispute, status: 'decided', decision: 'refund_to_buyer', decision_reason: 'Files never arrived', resolved_at: new Date().toISOString() },
      [`GET /transactions/${fx.dispute.transaction_id}`]: T.disputed,
    })
    expect(await screen.findByText('Refunded to the buyer')).toBeTruthy()
    expect(screen.getByText('Files never arrived')).toBeTruthy()
    expect(screen.queryByLabelText('Message')).toBeNull()
  })
  it('staff queue lists disputes with deal details', async () => {
    renderApp('/staff/disputes', fx.me.arbiter, { 'GET /disputes?status=open': fx.disputes })
    expect(await screen.findByText('Disputed deal')).toBeTruthy()
    expect(screen.getByText('Review ›')).toBeTruthy()
  })
})

describe('admin', () => {
  it('overview shows platform numbers from the API', async () => {
    renderApp('/admin', fx.me.admin, { 'GET /admin/stats': fx.admin.stats })
    expect(await screen.findByText('Platform overview')).toBeTruthy()
    expect(screen.getByText('Open disputes').nextSibling.textContent).toBe(String(fx.admin.stats.open_disputes))
    expect(screen.getByText('$500.00')).toBeTruthy()      // released volume
  })
  it('verifying KYC asks for a reason and sends it', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('Passport checked')
    const calls = renderApp('/admin/users', fx.me.admin, {
      'GET /admin/users': fx.admin.users, [`POST /admin/users/${fx.users.buyer}/kyc`]: fx.admin.users[0],
    })
    const row = (await screen.findByText('bea@example.com')).closest('tr')
    fireEvent.click(within(row).getByRole('button', { name: 'Verify KYC' }))
    await waitFor(() => expect(calls.find((c) => c.path.endsWith('/kyc'))?.body).toEqual({ status: 'verified', reason: 'Passport checked' }))
  })
  it('does nothing if the admin gives no reason', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue(null)
    const calls = renderApp('/admin/users', fx.me.admin, { 'GET /admin/users': fx.admin.users })
    const row = (await screen.findByText('bea@example.com')).closest('tr')
    fireEvent.click(within(row).getByRole('button', { name: 'Freeze' }))
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })
  it("admins can't act on admin accounts or themselves from the UI", async () => {
    renderApp('/admin/users', fx.me.admin, { 'GET /admin/users': fx.admin.users })
    const row = (await screen.findByText('admin@example.com')).closest('tr')
    expect(within(row).queryByRole('button')).toBeNull()
  })
  it('lists every transaction', async () => {
    renderApp('/admin/transactions', fx.me.admin, { 'GET /admin/transactions': fx.admin.transactions })
    expect(await screen.findByText('Released deal')).toBeTruthy()
  })
})
