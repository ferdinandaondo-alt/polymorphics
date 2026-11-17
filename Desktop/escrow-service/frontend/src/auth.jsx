import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, hasToken, setToken } from './api'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [signedOut, setSignedOut] = useState(false)   // true only after a deliberate Log out (vs. an expired session)
  const [loading, setLoading] = useState(hasToken())   // only wait for /auth/me if we have a token to check

  const loadMe = useCallback(async () => {
    try { setUser(await api.get('/auth/me')) } catch { setUser(null) } finally { setLoading(false) }
  }, [])

  useEffect(() => { if (hasToken()) loadMe() }, [loadMe])
  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('auth:logout', onLogout)
    return () => window.removeEventListener('auth:logout', onLogout)
  }, [])

  const login = async (email, password) => {
    const { access_token } = await api.post('/auth/login', { email, password })
    setToken(access_token)
    const me = await api.get('/auth/me')
    setUser(me)
    setSignedOut(false)
    return me
  }
  const register = async (full_name, email, password) => {
    await api.post('/auth/register', { full_name, email, password })
    return login(email, password)
  }
  const logout = () => { setToken(null); setUser(null); setSignedOut(true) }

  return <AuthContext.Provider value={{ user, loading, signedOut, login, register, logout }}>{children}</AuthContext.Provider>
}
