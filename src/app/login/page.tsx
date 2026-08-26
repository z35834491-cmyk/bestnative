'use client'

import { useState } from 'react'
import { useAuth } from '@/lib/auth'
import { LoadingSpinner } from '@/components/ui/AsyncState'

export default function LoginPage() {
  const { login, loading } = useAuth()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (loading) return <LoadingSpinner />

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await login(username, password)
      window.location.href = '/'
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-shark-bg">
      <form onSubmit={onSubmit} className="w-80 p-6 rounded-xl glass border border-shark-border space-y-4">
        <h1 className="text-lg font-bold text-white text-center">Shore 登录</h1>
        <input value={username} onChange={e => setUsername(e.target.value)} placeholder="用户名"
          className="w-full bg-slate-950/70 border border-shark-border rounded px-3 py-2 text-sm text-white" />
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="密码"
          className="w-full bg-slate-950/70 border border-shark-border rounded px-3 py-2 text-sm text-white" />
        {error && <p className="text-xs text-red-400">{error}</p>}
        <button type="submit" disabled={submitting}
          className="w-full py-2 rounded bg-shark-accent text-white text-sm font-medium disabled:opacity-50">
          {submitting ? '登录中…' : '登录'}
        </button>
        <p className="text-[10px] text-shark-muted text-center">开发环境 AUTH_REQUIRED=false 时可跳过</p>
      </form>
    </div>
  )
}
