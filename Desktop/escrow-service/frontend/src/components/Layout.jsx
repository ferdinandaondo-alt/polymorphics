import { NavLink, Outlet, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth'
import { Loading } from './ui'

export function homePath(user) {
  if (user?.role === 'admin') return '/admin'
  if (user?.role === 'arbiter') return '/staff/disputes'
  return '/'
}

export function RequireAuth() {
  const { user, loading, signedOut } = useAuth()
  const location = useLocation()
  if (loading) return <main className="page"><Loading /></main>
  if (!user) return <Navigate to="/login" replace state={signedOut ? undefined : { from: location.pathname }} />   /* expired session: come back to this page after logging in */
  return <Layout />
}

export function RequireRole({ roles, children }) {
  const { user } = useAuth()
  return roles.includes(user.role) ? children : <Navigate to={homePath(user)} replace />
}

function Layout() {
  const { user, logout } = useAuth()
  const link = ({ isActive }) => (isActive ? 'active' : undefined)
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <span className="brand">EscrowApp{user.role === 'admin' ? ' · Admin' : ''}</span>
          <nav aria-label="Main">
            {user.role === 'user' && (<>
              <NavLink to="/" end className={link}>My transactions</NavLink>
              <NavLink to="/new" className={link}>New transaction</NavLink>
            </>)}
            {user.role === 'arbiter' && <NavLink to="/staff/disputes" className={link}>Disputes</NavLink>}
            {user.role === 'admin' && (<>
              <NavLink to="/admin" end className={link}>Overview</NavLink>
              <NavLink to="/admin/users" className={link}>Users</NavLink>
              <NavLink to="/admin/transactions" className={link}>Transactions</NavLink>
              <NavLink to="/staff/disputes" className={link}>Disputes</NavLink>
            </>)}
          </nav>
          <div className="who">
            <span>{user.full_name}</span>
            {user.role !== 'user' && <span className="pill">{user.role}</span>}
            {user.role === 'user' && user.kyc_status !== 'verified' && <span className="pill pill-warn" title="Identity verification is required for larger deals">KYC: {user.kyc_status}</span>}
            <button className="btn btn-small" onClick={logout}>Log out</button>
          </div>
        </div>
      </header>
      <main className="page"><Outlet /></main>
    </>
  )
}
