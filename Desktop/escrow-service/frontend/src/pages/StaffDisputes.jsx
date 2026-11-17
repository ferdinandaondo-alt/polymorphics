import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Alert, Loading } from '../components/ui'
import { useLoad } from '../hooks'
import { fmtDate } from '../labels'
import { formatMoney } from '../money'

const TABS = [['open', 'Open'], ['decided', 'Decided'], ['', 'All']]

export default function StaffDisputes() {
  const [status, setStatus] = useState('open')
  const { data, error, loading } = useLoad(() => api.get(`/disputes${status ? `?status=${status}` : ''}`), [status])

  return (
    <>
      <div className="page-head"><div><h1>Disputes</h1><p className="muted">Oldest first. Open a case to review the evidence and decide.</p></div></div>
      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={label} role="tab" aria-selected={status === key} className={`tab ${status === key ? 'active' : ''}`} onClick={() => setStatus(key)}>{label}</button>
        ))}
      </div>
      {!data ? (loading ? <Loading /> : <Alert>{error}</Alert>) : data.length === 0 ? (
        <div className="card empty"><p>No {status || ''} disputes.</p></div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Deal</th><th>Buyer</th><th>Seller</th><th className="right">Amount</th><th>Opened</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.id}>
                  <td><strong>{d.transaction_title}</strong></td>
                  <td>{d.buyer_name}</td><td>{d.seller_name}</td>
                  <td className="right mono">{formatMoney(d.amount, d.currency)}</td>
                  <td className="small">{fmtDate(d.opened_at)}</td>
                  <td><span className={`badge badge-${d.status}`}>{d.status}</span></td>
                  <td className="right"><Link to={`/disputes/${d.id}`}>{d.status === 'open' ? 'Review ›' : 'View ›'}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
