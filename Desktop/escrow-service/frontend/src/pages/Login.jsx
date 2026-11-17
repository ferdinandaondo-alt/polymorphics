import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth'
import { homePath } from '../components/Layout'
import { Alert } from '../components/ui'

export default function Login() {
  const { user, login } = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={location.state?.from || homePath(user)} replace />

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError('')
    try { await login(email, password) } catch (err) { setError(err.message); setBusy(false) }
  }

  return (
    <div className="auth-box">
      <div className="center"><h1>EscrowApp</h1><p className="muted">Secure payments, held until both sides agree</p></div>
      <form className="card" onSubmit={submit}>
        <h2 className="center">Log in</h2>
        <label htmlFor="email">Email</label>
        <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <label htmlFor="password">Password</label>
        <input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        <Alert>{error}</Alert>
        <div className="btn-row"><button className="btn btn-primary" style={{ flex: 1 }} disabled={busy}>{busy ? 'Logging in…' : 'Log in'}</button></div>
        <p className="center small muted">No account? <Link to="/register">Sign up</Link></p>
      </form>
    </div>
  )
}
