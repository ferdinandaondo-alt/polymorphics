import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { homePath } from '../components/Layout'
import { Alert } from '../components/ui'

export default function Register() {
  const { user, register } = useAuth()
  const [form, setForm] = useState({ full_name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  if (user) return <Navigate to={homePath(user)} replace />

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError('')
    try { await register(form.full_name, form.email, form.password) } catch (err) { setError(err.message); setBusy(false) }
  }

  return (
    <div className="auth-box">
      <div className="center"><h1>Create your account</h1></div>
      <form className="card" onSubmit={submit}>
        <label htmlFor="name">Full name</label>
        <input id="name" required maxLength={255} autoComplete="name" value={form.full_name} onChange={set('full_name')} />
        <label htmlFor="email">Email</label>
        <input id="email" type="email" required autoComplete="email" value={form.email} onChange={set('email')} />
        <label htmlFor="password">Password (at least 8 characters)</label>
        <input id="password" type="password" required minLength={8} autoComplete="new-password" value={form.password} onChange={set('password')} />
        <Alert>{error}</Alert>
        <div className="btn-row"><button className="btn btn-primary" style={{ flex: 1 }} disabled={busy}>{busy ? 'Creating…' : 'Sign up'}</button></div>
        <p className="center small muted">Already registered? <Link to="/login">Log in</Link></p>
      </form>
    </div>
  )
}
