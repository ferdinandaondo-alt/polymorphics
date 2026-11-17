import { Link } from 'react-router-dom'
import { api } from '../api'
import { Alert, Loading, Stat } from '../components/ui'
import { useLoad } from '../hooks'
import { STATUS_LABEL } from '../labels'
import { formatMoney } from '../money'

export default function AdminOverview() {
  const { data: s, error, loading } = useLoad(() => api.get('/admin/stats'), [])
  if (!s) return loading ? <Loading /> : <Alert>{error}</Alert>
  const volume = Object.entries(s.released_volume_by_currency)
  return (
    <>
      <div className="page-head"><div><h1>Platform overview</h1></div></div>
      <div className="stats">
        <Stat label="Users" value={s.users} />
        <Stat label="Pending KYC" value={s.pending_kyc} hint={<Link to="/admin/users">Review users ›</Link>} />
        <Stat label="Open disputes" value={s.open_disputes} hint={<Link to="/staff/disputes">Go to queue ›</Link>} />
        <Stat label="Released volume" value={volume.length ? volume.map(([c, v]) => formatMoney(v, c)).join(' · ') : '—'} hint="Item prices of completed deals" />
      </div>
      <h2>Transactions by status</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Status</th><th className="right">Count</th></tr></thead>
          <tbody>{Object.entries(s.transactions_by_status).map(([k, n]) => (
            <tr key={k}><td><Link to={`/admin/transactions?status=${k}`}>{STATUS_LABEL[k] || k}</Link></td><td className="right mono">{n}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </>
  )
}
