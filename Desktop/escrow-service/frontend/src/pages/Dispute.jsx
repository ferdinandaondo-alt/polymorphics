import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Alert, Loading, StatusBadge } from '../components/ui'
import { useLoad } from '../hooks'
import { fmtDate, parseDate } from '../labels'
import { formatMoney, toMinor } from '../money'

const DECISION_LABEL = { release_to_seller: 'Released to the seller', refund_to_buyer: 'Refunded to the buyer', split: 'Split between both' }

export default function Dispute() {
  const { id } = useParams()
  const { user } = useAuth()
  const dq = useLoad(() => api.get(`/disputes/${id}`), [id])
  const d = dq.data
  const tq = useLoad(() => (d ? api.get(`/transactions/${d.transaction_id}`) : Promise.resolve(null)), [d?.transaction_id])
  const t = tq.data

  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [ev, setEv] = useState({ note: '', file_url: '' })
  const [dec, setDec] = useState({ decision: 'refund_to_buyer', reason: '', split: '' })

  if (!d) return dq.loading ? <Loading /> : <Alert>{dq.error}</Alert>
  if (!t) return tq.loading ? <Loading /> : <Alert>{tq.error}</Alert>

  const isParty = [t.buyer_id, t.seller_id].includes(user.id)
  const isStaff = ['arbiter', 'admin'].includes(user.role)
  const open = d.status === 'open'
  const deadline = parseDate(d.evidence_deadline)
  const evidenceOpen = open && deadline && deadline > new Date()
  const money = (n) => formatMoney(n, t.currency)
  const whoIs = (uid) => (uid === t.buyer_id ? `${t.buyer_name} (buyer)` : uid === t.seller_id ? `${t.seller_name} (seller)` : 'Arbiter')

  async function run(fn) {
    setBusy(true); setError('')
    try { await fn(); dq.reload(); tq.reload() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const sendMessage = (e) => { e.preventDefault(); run(async () => { await api.post(`/disputes/${id}/messages`, { content: msg }); setMsg('') }) }
  const sendEvidence = (e) => { e.preventDefault(); run(async () => { await api.post(`/disputes/${id}/evidence`, { note: ev.note || null, file_url: ev.file_url || null }); setEv({ note: '', file_url: '' }) }) }

  function decide(e) {
    e.preventDefault()
    const body = { decision: dec.decision, reason: dec.reason }
    if (dec.decision === 'split') {
      const minor = toMinor(dec.split, t.currency)
      if (!minor) return setError('Enter how much of the item price the seller keeps, e.g. 200.00')
      body.split_to_seller_amount = minor
    }
    if (!window.confirm(`Record this decision: "${DECISION_LABEL[dec.decision]}"? Money moves immediately and this cannot be undone.`)) return
    run(() => api.post(`/disputes/${id}/decision`, body))
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Dispute: {t.title} <span className={`badge badge-${d.status}`}>{d.status}</span></h1>
          <p className="muted">{t.buyer_name} (buyer) vs {t.seller_name} (seller) · {money(t.amount)} · <Link to={`/transactions/${t.id}`}>View transaction ›</Link></p>
        </div>
        {isParty ? <Link to={`/transactions/${t.id}`} className="btn">‹ Back</Link> : <Link to="/staff/disputes" className="btn">‹ All disputes</Link>}
      </div>

      <div className="grid-2">
        <div>
          <div className="card"><h2>Why it was opened</h2><p className="small muted">By {whoIs(d.opened_by_id)} on {fmtDate(d.opened_at)}</p><p style={{ whiteSpace: 'pre-wrap' }}>{d.reason}</p></div>

          <div className="card">
            <h2>Evidence</h2>
            {open && <p className="small muted">{evidenceOpen ? `Evidence can be added until ${fmtDate(d.evidence_deadline)}.` : 'The evidence deadline has passed.'}</p>}
            {d.evidence.length === 0 && <p className="muted">No evidence submitted yet.</p>}
            {d.evidence.map((e) => (
              <div className="evidence" key={e.id}>
                <div className="msg-who">{whoIs(e.uploaded_by_id)} · {fmtDate(e.created_at)}</div>
                {e.note && <div style={{ whiteSpace: 'pre-wrap' }}>{e.note}</div>}
                {e.file_url && <a href={e.file_url} target="_blank" rel="noopener noreferrer nofollow">{e.file_url}</a>}
              </div>
            ))}
            {isParty && evidenceOpen && (
              <form onSubmit={sendEvidence}>
                <label htmlFor="ev-note">Add a note</label>
                <textarea id="ev-note" value={ev.note} onChange={(e) => setEv({ ...ev, note: e.target.value })} />
                <label htmlFor="ev-url">Link to a file (optional)</label>
                <input id="ev-url" type="url" placeholder="https://…" value={ev.file_url} onChange={(e) => setEv({ ...ev, file_url: e.target.value })} />
                <div className="btn-row"><button className="btn" disabled={busy || (!ev.note && !ev.file_url)}>Add evidence</button></div>
              </form>
            )}
          </div>

          <div className="card">
            <h2>Messages</h2>
            {d.messages.length === 0 && <p className="muted">No messages yet.</p>}
            <div className="thread">
              {d.messages.map((m) => (
                <div key={m.id} className={`msg ${m.sender_id === user.id ? 'mine' : ''}`}>
                  <div className="msg-who">{whoIs(m.sender_id)} · {fmtDate(m.created_at)}</div>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
                </div>
              ))}
            </div>
            {open && (
              <form onSubmit={sendMessage} className="row">
                <input aria-label="Message" placeholder="Write a message…" value={msg} onChange={(e) => setMsg(e.target.value)} />
                <button className="btn" style={{ flex: 'none' }} disabled={busy || !msg.trim()}>Send</button>
              </form>
            )}
          </div>
        </div>

        <div>
          {!open && (
            <div className="card">
              <h2>Decision</h2>
              <p><strong>{DECISION_LABEL[d.decision]}</strong></p>
              {d.decision === 'split' && <p>Seller kept {money(d.split_to_seller_amount)} of the item price; the rest went back to the buyer.</p>}
              <p style={{ whiteSpace: 'pre-wrap' }}>{d.decision_reason}</p>
              <p className="small muted">Decided {fmtDate(d.resolved_at)}</p>
            </div>
          )}

          {open && isStaff && (
            <form className="card" onSubmit={decide}>
              <h2>Arbiter decision</h2>
              <div className="choices" style={{ flexDirection: 'column', gap: 0 }}>
                <label><input type="radio" name="dec" checked={dec.decision === 'release_to_seller'} onChange={() => setDec({ ...dec, decision: 'release_to_seller' })} />Release to seller — they receive {money(t.seller_net)}</label>
                <label><input type="radio" name="dec" checked={dec.decision === 'refund_to_buyer'} onChange={() => setDec({ ...dec, decision: 'refund_to_buyer' })} />Refund buyer in full — {money(t.buyer_charge)} returned</label>
                <label><input type="radio" name="dec" checked={dec.decision === 'split'} onChange={() => setDec({ ...dec, decision: 'split' })} />Split the item price</label>
              </div>
              {dec.decision === 'split' && (
                <>
                  <label htmlFor="split">Seller keeps (of the {money(t.amount)} item price)</label>
                  <input id="split" inputMode="decimal" placeholder="0.00" value={dec.split} onChange={(e) => setDec({ ...dec, split: e.target.value })} />
                  <p className="small muted">The buyer gets back the rest. The platform fee is kept in full.</p>
                </>
              )}
              <label htmlFor="why">Reason (required — both parties will see it)</label>
              <textarea id="why" required minLength={5} value={dec.reason} onChange={(e) => setDec({ ...dec, reason: e.target.value })} />
              <div className="btn-row"><button className="btn btn-primary" disabled={busy}>Submit decision</button></div>
            </form>
          )}
          {open && isParty && <Alert kind="info">An arbiter will review the evidence and messages and decide. You'll be able to see the outcome here.</Alert>}
          {open && isStaff && !isParty && null}
          <Alert>{error}</Alert>
        </div>
      </div>
    </>
  )
}
