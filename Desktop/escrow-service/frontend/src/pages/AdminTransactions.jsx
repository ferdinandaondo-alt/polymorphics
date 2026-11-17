import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Alert, Loading, StatusBadge } from '../components/ui'
import { useLoad } from '../hooks'
import { STATUS_LABEL, fmtDate } from '../labels'
import { formatMoney } from '../money'

export default function AdminTransactions() {
  const [params, setParams] = useSearchParams()
  const status = params.get('status') || ''
  const { data, error, loading } = useLoad(() => api.get(`/admin/transactions${status ? `?status=${status}` : ''}`), [status])
  return (
    <>
      <div className="page-head"><div><h1>All transactions</h1><p className="muted">Showing the 200 most recent.</p></div></div>
      <label htmlFor="st" style={{ maxWidth: 260 }}>Filter by status</label>
      <select id="st" style={{ maxWidth: 260, marginBottom: '1rem' }} value={status} onChange={(e) => setParams(e.target.value ? { status: e.target.value } : {})}>
        <option value="">All</option>
        {Object.entries(STATUS_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      {!data ? (loading ? <Loading /> : <Alert>{error}</Alert>) : data.length === 0 ? <div className="card empty">No transactions.</div> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Title</th><th>Buyer</th><th>Seller</th><th className="right">Amount</th><th>Status</th><th>Created</th><th></th></tr></thead>
            <tbody>{data.map((t) => (
              <tr key={t.id}>
                <td><strong>{t.title}</strong></td><td>{t.buyer_name}</td><td>{t.seller_name}</td>
                <td className="right mono">{formatMoney(t.amount, t.currency)}</td>
                <td><StatusBadge status={t.status} /></td><td className="small">{fmtDate(t.created_at)}</td>
                <td className="right"><Link to={`/transactions/${t.id}`}>Open ›</Link></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </>
  )
}
