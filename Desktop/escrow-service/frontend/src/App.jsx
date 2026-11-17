import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import { RequireAuth, RequireRole, homePath } from './components/Layout'
import AdminOverview from './pages/AdminOverview'
import AdminTransactions from './pages/AdminTransactions'
import AdminUsers from './pages/AdminUsers'
import Dashboard from './pages/Dashboard'
import Dispute from './pages/Dispute'
import Login from './pages/Login'
import NewTransaction from './pages/NewTransaction'
import Register from './pages/Register'
import StaffDisputes from './pages/StaffDisputes'
import TransactionDetail from './pages/TransactionDetail'

function Home() {
  const { user } = useAuth()
  return user.role === 'user' ? <Dashboard /> : <Navigate to={homePath(user)} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<Home />} />
        <Route path="/new" element={<RequireRole roles={['user']}><NewTransaction /></RequireRole>} />
        <Route path="/transactions/:id" element={<TransactionDetail />} />
        <Route path="/disputes/:id" element={<Dispute />} />
        <Route path="/staff/disputes" element={<RequireRole roles={['arbiter', 'admin']}><StaffDisputes /></RequireRole>} />
        <Route path="/admin" element={<RequireRole roles={['admin']}><AdminOverview /></RequireRole>} />
        <Route path="/admin/users" element={<RequireRole roles={['admin']}><AdminUsers /></RequireRole>} />
        <Route path="/admin/transactions" element={<RequireRole roles={['admin']}><AdminTransactions /></RequireRole>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
