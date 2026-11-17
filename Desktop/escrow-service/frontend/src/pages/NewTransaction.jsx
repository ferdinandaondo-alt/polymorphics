import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Alert } from '../components/ui'
import { useLoad } from '../hooks'
import { estimateFee, formatMoney, toMinor } from '../money'

const CURRENCIES = ['USD', 'EUR', 'GBP', 'KES', 'NGN', 'ZAR', 'INR', 'CAD', 'AUD']

export default function NewTransaction() {
  const { user } = useAuth()
  const nav = useNavigate()
  const cfg = useLoad(() => api.get('/config'), []).data
  const [f, setF] = useState({
    title: '', description: '', amount: '', currency: 'USD', my_role: 'buyer',
    counterparty_email: '', fee_payer: 'buyer', deadline: '', release_days: 5,
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const amount = toMinor(f.amount, f.currency)
  const fee = amount && cfg ? estimateFee(amount, cfg.platform_fee_bps) : 0
  const buyerShare = f.fee_payer === 'buyer' ? fee : f.fee_payer === 'split' ? fee - Math.floor(fee / 2) : 0
  const sellerShare = fee - buyerShare
  const needsKyc = amount && cfg && amount > cfg.kyc_threshold && user.kyc_status !== 'verified'

  async function submit(e) {
    e.preventDefault()
    setError('')
    if (!amount) return setError('Enter a valid amount greater than zero (e.g. 150.00).')
    setBusy(true)
    try {
      const t = await api.post('/transactions', {
        counterparty_email: f.counterparty_email.trim(), my_role: f.my_role, title: f.title.trim(),
        description: f.description.trim() || null, currency: f.currency, amount, fee_payer: f.fee_payer,
        delivery_deadline: f.deadline ? new Date(`${f.deadline}T23:59:59`).toISOString() : null,
        auto_release_hours: Number(f.release_days) * 24,
      })
      nav(`/transactions/${t.id}`)
    } catch (err) { setError(err.message); setBusy(false) }
  }

  return (
    <>
      <div className="page-head"><div><h1>New escrow transaction</h1><p className="muted">The other person must already have an account, and will be asked to accept.</p></div></div>
      <form className="grid-2" onSubmit={submit}>
        <div className="card">
          <label htmlFor="title">Title</label>
          <input id="title" required maxLength={255} placeholder="e.g. Website redesign" value={f.title} onChange={set('title')} />
          <label htmlFor="desc">Description (what exactly is being delivered?)</label>
          <textarea id="desc" maxLength={5000} value={f.description} onChange={set('description')} />
          <div className="row">
            <div><label htmlFor="amount">Amount</label><input id="amount" required inputMode="decimal" placeholder="0.00" value={f.amount} onChange={set('amount')} /></div>
            <div><label htmlFor="currency">Currency</label><select id="currency" value={f.currency} onChange={set('currency')}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></div>
          </div>
          <label>I am the</label>
          <div className="choices">
            {['buyer', 'seller'].map((r) => <label key={r}><input type="radio" name="role" checked={f.my_role === r} onChange={() => setF({ ...f, my_role: r })} />{r === 'buyer' ? 'Buyer (I pay)' : 'Seller (I deliver)'}</label>)}
          </div>
          <label htmlFor="cp">{f.my_role === 'buyer' ? "Seller's" : "Buyer's"} email</label>
          <input id="cp" type="email" required placeholder="name@example.com" value={f.counterparty_email} onChange={set('counterparty_email')} />
          <label>Who pays the platform fee?</label>
          <div className="choices">
            {[['buyer', 'Buyer'], ['seller', 'Seller'], ['split', 'Split 50/50']].map(([v, l]) => <label key={v}><input type="radio" name="fee" checked={f.fee_payer === v} onChange={() => setF({ ...f, fee_payer: v })} />{l}</label>)}
          </div>
          <div className="row">
            <div><label htmlFor="deadline">Delivery deadline (optional)</label><input id="deadline" type="date" value={f.deadline} onChange={set('deadline')} /></div>
            <div><label htmlFor="rel">Auto-release after delivery</label>
              <select id="rel" value={f.release_days} onChange={set('release_days')}>{[1, 3, 5, 7, 14, 30].map((d) => <option key={d} value={d}>{d} day{d > 1 ? 's' : ''}</option>)}</select></div>
          </div>
          <p className="small muted">If the buyer neither approves nor opens a dispute within this window after delivery, the money is released to the seller.</p>
        </div>

        <div>
          <div className="card">
            <h2>Summary</h2>
            <div className="kv">
              <span>Amount</span><span className="mono">{amount ? formatMoney(amount, f.currency) : '—'}</span>
              <span>Platform fee{cfg ? ` (${cfg.platform_fee_bps / 100}%)` : ''}</span><span className="mono">{amount ? formatMoney(fee, f.currency) : '—'}</span>
              <span>Buyer pays</span><span className="mono">{amount ? formatMoney(amount + buyerShare, f.currency) : '—'}</span>
              <span className="total">Seller receives</span><span className="total mono">{amount ? formatMoney(amount - sellerShare, f.currency) : '—'}</span>
            </div>
            <p className="small muted">Estimate — the exact figures are confirmed once the transaction is created.</p>
          </div>
          {needsKyc && <Alert kind="info">Deals of this size need identity verification (KYC) first. Your account is "{user.kyc_status}", so the server will decline this until an admin verifies you.</Alert>}
          <Alert>{error}</Alert>
          <div className="btn-row">
            <button className="btn btn-primary" disabled={busy}>{busy ? 'Creating…' : 'Send to counterparty'}</button>
            <Link to="/" className="btn">Cancel</Link>
          </div>
        </div>
      </form>
    </>
  )
}
