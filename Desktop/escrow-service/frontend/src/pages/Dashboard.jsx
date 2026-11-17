import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Alert, Loading, Stat, StatusBadge } from '../components/ui'
import { useLoad } from '../hooks'
import { isFinished, needsMyAction } from '../labels'
import { formatMoney } from '../money'

const TABS = [['all', 'All'], ['action', 'Needs my action'], ['active', 'In progress'], ['done', 'Completed']]

export default function Dashboard() {
  const { user } = useAuth()
  const { data, error, loading } = useLoad(() => api.get('/transactions'), [])
  const [tab, setTab] = useState('all')

  if (!data) return loading ? <Loading /> : <Alert>{error}</Alert>

  const action = data.filter((t) => needsMyAction(t, user.id))
  const done = data.filter(isFinished)
  const active = data.filter((t) => !isFinished(t))
  const shown = { all: data, action, active, done }[tab]

  return (
    <>
      <div className="page-head">
        <div><h1>My transactions</h1><p className="muted">Everything you're buying or selling through escrow.</p></div>
        <Link to="/new" className="btn btn-primary">+ New transaction</Link>
      </div>

      <div className="stats">
        <Stat label="In progress" value={active.length} />
        <Stat label="Needs your action" value={action.length} />
        <Stat label="Completed" value={done.length} />
      </div>

      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={`tab ${tab === key ? 'active' : ''}`} onClick={() => setTab(key)}>{label}</button>
        ))}
      </div>

      {shown.length === 0 ? (
        <div className="card empty">
          <p>{data.length === 0 ? "You don't have any transactions yet." : 'Nothing here.'}</p>
          {data.length === 0 && <Link to="/new" className="btn btn-primary">Start your first escrow</Link>}
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Title</th><th>Counterparty</th><th className="right">Amount</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {shown.map((t) => (
                <tr key={t.id}>
                  <td><strong>{t.title}</strong></td>
                  <td>{t.buyer_id === user.id ? `Seller: ${t.seller_name}` : `Buyer: ${t.buyer_name}`}</td>
                  <td className="right mono">{formatMoney(t.amount, t.currency)}</td>
                  <td>
                    <StatusBadge status={t.status} />
                    {needsMyAction(t, user.id) && <span className="badge" style={{ marginLeft: 6, background: '#fde68a', color: '#7a4b00' }}>Your turn</span>}
                  </td>
                  <td className="right"><Link to={`/transactions/${t.id}`}>View ›</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
