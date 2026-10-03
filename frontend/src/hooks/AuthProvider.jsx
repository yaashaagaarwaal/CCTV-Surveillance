import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { AuthContext } from './useAuth'

const ANONYMOUS = { status: 'anonymous', user: null }

// Who is logged in. The session itself lives in an HttpOnly cookie that page
// scripts cannot read; this only remembers the user's name and role for the UI.
// (Hiding controls from viewers is a convenience — the server enforces roles.)
export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: 'loading', user: null })

  useEffect(() => {
    api
      .me()
      .then((user) => setState({ status: 'authenticated', user }))
      .catch(() => setState(ANONYMOUS))
  }, [])

  useEffect(() => {
    const onUnauthorized = () => setState(ANONYMOUS)
    window.addEventListener('auth:unauthorized', onUnauthorized)
    return () => window.removeEventListener('auth:unauthorized', onUnauthorized)
  }, [])

  const login = useCallback(async (username, password) => {
    const user = await api.login(username, password)
    setState({ status: 'authenticated', user })
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setState(ANONYMOUS)
    }
  }, [])

  const value = useMemo(
    () => ({ ...state, isAdmin: state.user?.role === 'admin', login, logout }),
    [state, login, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
