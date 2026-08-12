'use client'

import { useCallback, useEffect, useState } from 'react'
import { BookOpen, Search, Lightbulb, Loader2, WifiOff, Brain, FileText, Bug, AlertTriangle } from 'lucide-react'
import { cn, fmtTime } from '@/lib/utils'

const API = ''

interface Incident {
  id: string; title: string; severity: string; status: string; affectedServices: string[]; source: string; createdAt: string; resolvedAt: string | null
}

export default function KnowledgePage() {
  const [resolved, setResolved] = useState<Incident[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const fetchResolved = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [rRes, aRes] = await Promise.all([
        fetch(`${API}/api/incidents?status=resolved&limit=50`),
        fetch(`${API}/api/incidents?status=analyzed&limit=50`),
      ])
      const r = await rRes.json()
      const a = await aRes.json()
      setResolved([...(Array.isArray(r) ? r : []), ...(Array.isArray(a) ? a : [])])
    } catch (e) {
      setError(e instanceof Error ? e.message : '无法连接 API')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchResolved() }, [fetchResolved])

  const filtered = resolved.filter(i =>
    !search || i.title.toLowerCase().includes(search.toLowerCase()) ||
    (i.affectedServices || []).some(s => s.toLowerCase().includes(search.toLowerCase()))
  )

  if (error && resolved.length === 0) {
    return <div className="h-full flex items-center justify-center"><div className="text-center space-y-3"><WifiOff size={40} className="text-red-400 mx-auto" /><p className="text-sm text-shark-muted">{error}</p><button onClick={fetchResolved} className="text-xs text-shark-accent border border-shark-accent/30 px-3 py-1.5 rounded">重试</button></div></div>
  }

  if (loading) return <div className="h-full flex items-center justify-center"><Loader2 size={32} className="animate-spin text-shark-accent" /></div>

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2"><BookOpen size={16} className="text-blue-400" /> 知识库</h1>
        <div className="ml-4 flex-1 max-w-md relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-shark-muted" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索历史事件、漏洞模式..." className="w-full bg-shark-bg border border-shark-border rounded-lg pl-9 pr-4 py-1.5 text-xs text-white placeholder-shark-muted/50 outline-none focus:border-shark-accent" />
        </div>
        <button onClick={fetchResolved} className="ml-auto text-xs text-shark-muted hover:text-white">刷新</button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        {filtered.length === 0 && <p className="text-sm text-shark-muted">{search ? '无匹配结果' : '暂无已解决的事件。事件解决后自动沉淀到知识库。'}</p>}

        <div className="space-y-4">
          {filtered.map(inc => (
            <div key={inc.id} className="glass rounded-xl p-5 border border-shark-border hover:border-shark-accent/30 transition-colors">
              <div className="flex items-center gap-2 mb-2">
                <span className={cn(
                  'px-2 py-0.5 rounded text-[10px] font-medium border',
                  inc.severity === 'critical' ? 'text-red-400 border-red-400/30 bg-red-400/5' : 'text-amber-400 border-amber-400/30 bg-amber-400/5'
                )}>{inc.severity === 'critical' ? '紧急' : '警告'}</span>
                <span className="text-sm font-medium text-white">{inc.title}</span>
                <span className="ml-auto text-[10px] text-shark-muted">{fmtTime(inc.createdAt)}</span>
              </div>
              <div className="flex items-center gap-4 text-xs text-shark-muted mb-3">
                <span className="flex items-center gap-1"><AlertTriangle size={12} /> {inc.affectedServices?.join(', ') || inc.source}</span>
                <span>{inc.source}</span>
                <span className={cn(inc.status === 'resolved' ? 'text-emerald-400' : 'text-shark-accent')}>{inc.status === 'resolved' ? '已解决' : '已分析'}</span>
                {inc.resolvedAt && <span>解决于 {fmtTime(inc.resolvedAt)}</span>}
              </div>
              <div className="flex gap-2">
                <span className="text-[10px] flex items-center gap-1 text-shark-accent bg-shark-accent/5 px-2 py-1 rounded border border-shark-accent/10">
                  <Brain size={12} /> AI 根因分析
                </span>
                <span className="text-[10px] flex items-center gap-1 text-purple-400 bg-purple-400/5 px-2 py-1 rounded border border-purple-400/10">
                  <FileText size={12} /> 复盘报告
                </span>
                <span className="text-[10px] flex items-center gap-1 text-amber-400 bg-amber-400/5 px-2 py-1 rounded border border-amber-400/10">
                  <Lightbulb size={12} /> 经验沉淀
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
