import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Alert, Loading, Stepper, StatusBadge } from '../components/ui'
import { useLoad } from '../hooks'
import { ENTRY_LABEL, accountLabel, fmtDate } from '../labels'
import { formatMoney } from '../money'

export default function TransactionDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const nav = useNavigate()
  const tx = useLoad(() => api.get(`/transactions/${id}`), [id])
  const ledger = useLoad(() => api.get(`/transactions/${id}/ledger`), [id])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [disputing, setDisputing] = useState(false)
  const [reason, setReason] = useState('')

  const t = tx.data
  if (!t) return tx.loading ? <Loading /> : <Alert>{tx.error}</Alert>

  const isBuyer = t.buyer_id === user.id
  const isSeller = t.seller_id === user.id
  const isParty = isBuyer || isSeller
  const iCreated = t.created_by_id === user.id
  const money = (n) => formatMoney(n, t.currency)
  const other = isBuyer ? t.seller_name : t.buyer_name

  async function act(path, body, confirmMsg) {
    if (confirmMsg && !window.confirm(confirmMsg)) return
    setBusy(true); setError('')
    try { await api.post(`/transactions/${id}/${path}`, body); tx.reload(); ledger.reload() }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  async function openDispute(e) {
    e.preventDefault()
    setBusy(true); setError('')
    try { const d = await api.post(`/transactions/${id}/dispute`, { reason }); nav(`/disputes/${d.id}`) }
    catch (err) { setError(err.message); setBusy(false) }
  }

  const canDispute = isParty && ['funded', 'delivered'].includes(t.status)

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t.title} <StatusBadge status={t.status} /></h1>
          <p className="muted">Buyer: {t.buyer_name} · Seller: {t.seller_name} · {money(t.amount)}{t.delivery_deadline ? ` · Deadline: ${fmtDate(t.delivery_deadline)}` : ''}</p>
        </div>
        <Link to={isParty ? '/' : -1} className="btn">‹ Back</Link>
      </div>

      {!['cancelled', 'expired', 'refunded'].includes(t.status) && <Stepper status={t.status === 'disputed' ? 'funded' : t.status} />}
      {t.status === 'disputed' && <Alert kind="info">This transaction is in dispute. Funds stay in escrow until an arbiter decides. {t.dispute_id && <Link to={`/disputes/${t.dispute_id}`}>Open the dispute ›</Link>}</Alert>}
      {t.status === 'refunded' && <Alert kind="info">The buyer was refunded in full. {t.dispute_id && <Link to={`/disputes/${t.dispute_id}`}>See the arbiter's decision ›</Link>}</Alert>}
      {t.status === 'cancelled' && <Alert kind="info">This transaction was cancelled before any money moved.</Alert>}
      {t.status === 'released' && <Alert kind="ok">Funds have been released to the seller. {t.dispute_id && <Link to={`/disputes/${t.dispute_id}`}>See the dispute ›</Link>}</Alert>}

      <div className="grid-2">
        <div>
          <div className="card">
            <h2>Description</h2>
            <p style={{ whiteSpace: 'pre-wrap' }}>{t.description || <span className="muted">No description provided.</span>}</p>
          </div>

          <div className="card">
            <h2>Money movements</h2>
            {!ledger.data ? <Loading /> : ledger.data.length === 0 ? <p className="muted">No money has moved yet.</p> : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>When</th><th>Type</th><th>Account</th><th className="right">Debit</th><th className="right">Credit</th></tr></thead>
                  <tbody>
                    {ledger.data.map((e) => (
                      <tr key={e.id}>
                        <td className="small">{fmtDate(e.created_at)}</td>
                        <td>{ENTRY_LABEL[e.entry_type] || e.entry_type}</td>
                        <td>{accountLabel(e.account)}</td>
                        <td className="right mono">{e.direction === 'debit' ? money(e.amount) : ''}</td>
                        <td className="right mono">{e.direction === 'credit' ? money(e.amount) : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div>
          <div className="card">
            <h2>Amounts</h2>
            <div className="kv">
              <span>Item price</span><span className="mono">{money(t.amount)}</span>
              <span>Platform fee ({t.fee_payer === 'split' ? 'split' : `paid by ${t.fee_payer}`})</span><span className="mono">{money(t.fee_amount)}</span>
              <span>Buyer pays</span><span className="mono">{money(t.buyer_charge)}</span>
              <span className="total">Seller receives</span><span className="total mono">{money(t.seller_net)}</span>
            </div>
          </div>

          {isParty && (
            <div className="card">
              <h2>What happens next</h2>

              {t.status === 'draft' && (iCreated
                ? <p>Waiting for <strong>{other}</strong> to accept.</p>
                : <><p><strong>{other}</strong> proposed this deal. Review the amounts, then accept or decline.</p>
                  <div className="btn-row">
                    <button className="btn btn-primary" disabled={busy} onClick={() => act('accept')}>Accept</button>
                    <button className="btn btn-danger" disabled={busy} onClick={() => act('cancel', {}, 'Decline this transaction?')}>Decline</button>
                  </div></>)}
              {t.status === 'draft' && iCreated && <div className="btn-row"><button className="btn btn-danger" disabled={busy} onClick={() => act('cancel', {}, 'Cancel this transaction?')}>Cancel transaction</button></div>}

              {t.status === 'accepted' && (isBuyer
                ? <><p>Both sides agreed. Pay <strong>{money(t.buyer_charge)}</strong> into escrow — the seller can't touch it until you approve delivery.</p>
                  <Alert kind="info">Payments are simulated in this version: no real money moves.</Alert>
                  <div className="btn-row">
                    <button className="btn btn-primary" disabled={busy} onClick={() => act('fund')}>Pay {money(t.buyer_charge)} into escrow</button>
                    <button className="btn btn-danger" disabled={busy} onClick={() => act('cancel', {}, 'Cancel this transaction?')}>Cancel</button>
                  </div></>
                : <><p>Waiting for <strong>{other}</strong> to fund the escrow. Don't start work until the status says Funded.</p>
                  <div className="btn-row"><button className="btn btn-danger" disabled={busy} onClick={() => act('cancel', {}, 'Cancel this transaction?')}>Cancel</button></div></>)}

              {t.status === 'funded' && (isSeller
                ? <><p>The money is safely in escrow. Do the work, then mark it delivered.</p>
                  <label htmlFor="note">Delivery note (optional)</label>
                  <textarea id="note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Link to files, tracking number, etc." />
                  <div className="btn-row"><button className="btn btn-primary" disabled={busy} onClick={() => act('deliver', { note: note || null })}>Mark as delivered</button></div></>
                : <p>Your payment is held in escrow. Waiting for <strong>{other}</strong> to deliver.</p>)}

              {t.status === 'delivered' && (isBuyer
                ? <><p>The seller says it's delivered. Check it carefully, then approve to release the money.</p>
                  <div className="btn-row"><button className="btn btn-primary" disabled={busy} onClick={() => act('approve', {}, `Release ${money(t.seller_net)} to ${t.seller_name}? This can't be undone.`)}>Approve &amp; release funds</button></div></>
                : <p>Waiting for <strong>{other}</strong> to approve.</p>)}
              {t.status === 'delivered' && t.auto_release_at && (
                <p className="small muted">{isBuyer ? 'If you do nothing, the funds are released automatically on' : 'If the buyer does nothing, the funds are released to you automatically on'} {fmtDate(t.auto_release_at)}.</p>)}

              {canDispute && !disputing && <div className="btn-row"><button className="btn" disabled={busy} onClick={() => setDisputing(true)}>Open a dispute</button></div>}
              {canDispute && disputing && (
                <form onSubmit={openDispute}>
                  <label htmlFor="reason">What went wrong? (min 5 characters)</label>
                  <textarea id="reason" required minLength={5} value={reason} onChange={(e) => setReason(e.target.value)} />
                  <p className="small muted">Funds are frozen and auto-release stops until an arbiter decides.</p>
                  <div className="btn-row"><button className="btn btn-danger" disabled={busy}>Submit dispute</button><button type="button" className="btn" onClick={() => setDisputing(false)}>Never mind</button></div>
                </form>)}

              {['released', 'refunded', 'cancelled', 'expired'].includes(t.status) && <p className="muted">Nothing more to do — this transaction is finished.</p>}
              <Alert>{error}</Alert>
            </div>
          )}
          {!isParty && <Alert kind="info">You're viewing this as {user.role}. Only the buyer and seller can act on it.</Alert>}
        </div>
      </div>
    </>
  )
}
