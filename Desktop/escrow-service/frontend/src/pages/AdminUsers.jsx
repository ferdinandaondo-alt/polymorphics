import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { Alert, Loading, askReason } from '../components/ui'
import { useLoad } from '../hooks'

export default function AdminUsers() {
  const { user: me } = useAuth()
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const { data, error, loading, reload } = useLoad(() => api.get(`/admin/users${q ? `?search=${encodeURIComponent(q)}` : ''}`), [q])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  async function act(u, path, body, prompt) {
    const reason = askReason(prompt)
    if (!reason) return
    setErr(''); setMsg('')
    try { await api.post(`/admin/users/${u.id}/${path}`, { ...body, reason }); setMsg(`Updated ${u.email}.`); reload() }
    catch (e) { setErr(e.message) }
  }

  return (
    <>
      <div className="page-head"><div><h1>Users</h1><p className="muted">Every change here is recorded in the audit log with your reason.</p></div></div>
      <form className="row" style={{ maxWidth: 480, marginBottom: '1rem' }} onSubmit={(e) => { e.preventDefault(); setQ(search.trim()) }}>
        <input aria-label="Search users" placeholder="Search by name or email" value={search} onChange={(e) => setSearch(e.target.value)} />
        <button className="btn" style={{ flex: 'none' }}>Search</button>
      </form>
      <Alert kind="ok">{msg}</Alert><Alert>{err}</Alert>
      {!data ? (loading ? <Loading /> : <Alert>{error}</Alert>) : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>KYC</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {data.map((u) => (
                <tr key={u.id}>
                  <td>{u.full_name}</td><td>{u.email}</td><td>{u.role}</td><td>{u.kyc_status}</td>
                  <td>{u.is_active ? 'Active' : <strong style={{ color: 'var(--bad)' }}>Frozen</strong>}</td>
                  <td>
                    {u.id === me.id || u.role === 'admin' ? <span className="muted small">—</span> : (
                      <div className="btn-row" style={{ marginTop: 0 }}>
                        {u.kyc_status !== 'verified' && <button className="btn btn-small" onClick={() => act(u, 'kyc', { status: 'verified' }, `Mark ${u.email} as KYC verified?`)}>Verify KYC</button>}
                        {u.kyc_status !== 'rejected' && <button className="btn btn-small" onClick={() => act(u, 'kyc', { status: 'rejected' }, `Reject KYC for ${u.email}?`)}>Reject KYC</button>}
                        <button className="btn btn-small btn-danger" onClick={() => act(u, 'freeze', { frozen: u.is_active }, `${u.is_active ? 'Freeze' : 'Unfreeze'} ${u.email}?`)}>{u.is_active ? 'Freeze' : 'Unfreeze'}</button>
                        <button className="btn btn-small" onClick={() => act(u, 'role', { role: u.role === 'arbiter' ? 'user' : 'arbiter' }, `Make ${u.email} ${u.role === 'arbiter' ? 'a regular user' : 'an arbiter'}?`)}>{u.role === 'arbiter' ? 'Remove arbiter' : 'Make arbiter'}</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
