'use client'

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { apiJson, clearToken, getToken, login as doLogin } from '@/lib/api'

type User = { username: string; displayName: string; role: string }

const AuthCtx = createContext<{
  user: User | null
  loading: boolean
  login: (u: string, p: string) => Promise<void>
  logout: () => void
}>({ user: null, loading: true, login: async () => {}, logout: () => {} })

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    if (!getToken()) { setUser(null); setLoading(false); return }
    try {
      const me = await apiJson<{ username: string; displayName: string; role: string }>('/api/auth/me')
      setUser(me)
    } catch {
      clearToken()
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const login = async (username: string, password: string) => {
    await doLogin(username, password)
    await refresh()
  }

  const logout = () => { clearToken(); setUser(null) }

  return (
    <AuthCtx.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthCtx.Provider>
  )
}

export function useAuth() { return useContext(AuthCtx) }
