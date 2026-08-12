'use client'

import { useEffect, useState } from 'react'
import { Settings, Loader2, WifiOff, Server, Database, Shield, Key, Globe, Cpu } from 'lucide-react'
import { cn, fmtTime } from '@/lib/utils'

const API = ''

export default function SettingsPage() {
  const [health, setHealth] = useState<{ app?: string; version?: string; environment?: string } | null>(null)
  const [ready, setReady] = useState<{ checks?: { database?: string } } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetch(`${API}/api/health`).then(r => r.json()),
      fetch(`${API}/api/ready`).then(r => r.json()),
    ]).then(([h, r]) => { setHealth(h); setReady(r) }).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [])

  if (error && !health) {
    return <div className="h-full flex items-center justify-center"><div className="text-center space-y-3"><WifiOff size={40} className="text-red-400 mx-auto" /><p className="text-sm text-shark-muted">{error}</p></div></div>
  }

  if (loading) return <div className="h-full flex items-center justify-center"><Loader2 size={32} className="animate-spin text-shark-accent" /></div>

  const configRows = [
    { icon: Server, label: '应用版本', value: `${health?.app || 'BestNative'} v${health?.version || '?'}` },
    { icon: Globe, label: '运行环境', value: String(health?.environment || '?') },
    { icon: Database, label: '数据库', value: ready?.checks?.database === 'ok' ? '已连接 ✅' : '未连接 ❌' },
    { icon: Cpu, label: 'LLM', value: 'DeepSeek v4-pro (deepseek-chat)' },
    { icon: Key, label: 'Embedding', value: 'bge-small-zh-v1.5 (本地 512维)' },
    { icon: Shield, label: '安全扫描', value: 'nmap + nuclei + subfinder + httpx' },
    { icon: Database, label: '向量库', value: 'pgvector (PostgreSQL 统一存储)' },
    { icon: Server, label: '发现引擎', value: 'K8s / AWS / SSH-VM (可插拔)' },
    { icon: Settings, label: '部署模式', value: 'Docker Compose · 单环境独立部署' },
  ]

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2"><Settings size={16} className="text-shark-muted" /> 系统设置</h1>
        <span className="ml-3 text-xs text-shark-muted">当前运行配置（只读）</span>
      </header>

      <div className="flex-1 overflow-auto p-6 max-w-3xl">
        <div className="glass rounded-xl p-5 mb-6">
          <h3 className="text-sm font-semibold text-white mb-4">系统信息</h3>
          <div className="space-y-0">
            {configRows.map((row, i) => (
              <div key={i} className={cn('flex items-center gap-4 py-3', i < configRows.length - 1 && 'border-b border-shark-border')}>
                <row.icon size={16} className="text-shark-muted shrink-0" />
                <span className="text-sm text-shark-muted w-28 shrink-0">{row.label}</span>
                <span className="text-sm text-white font-medium">{row.value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="glass rounded-xl p-5 border border-shark-accent/10">
          <h3 className="text-sm font-semibold text-white mb-2">配置方式</h3>
          <p className="text-xs text-shark-muted leading-relaxed">
            以上配置通过 <code className="text-shark-accent bg-shark-accent/5 px-1 rounded">backend/.env</code> 环境变量注入。
            修改后执行 <code className="text-shark-accent bg-shark-accent/5 px-1 rounded">docker compose up -d --build</code> 生效。
            详细说明参见 <code className="text-shark-accent bg-shark-accent/5 px-1 rounded">docs/INTEGRATION.md</code>。
          </p>
        </div>
      </div>
    </div>
  )
}
