'use client'

import { useCallback, useEffect, useState } from 'react'
import { BookOpen, Search } from 'lucide-react'
import { apiJson } from '@/lib/api'
import { ErrorState, LoadingSpinner } from '@/components/ui/AsyncState'

interface KnowledgeHit {
  id: string
  source_type: string
  title: string
  content: string
  score: number
  metadata?: Record<string, unknown>
}

export default function KnowledgePage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<KnowledgeHit[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const search = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); return }
    setLoading(true)
    setError(null)
    try {
      const data = await apiJson<{ results: KnowledgeHit[] }>(`/api/knowledge/search?q=${encodeURIComponent(q)}`)
      setResults(data.results || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : '搜索失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const t = setTimeout(() => search(query), 400)
    return () => clearTimeout(t)
  }, [query, search])

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2">
          <BookOpen size={16} className="text-blue-400" /> 知识库
        </h1>
        <div className="ml-4 flex-1 max-w-md relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-shark-muted" />
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="RAG 混合检索：根因、服务名、故障模式…"
            className="w-full bg-shark-bg border border-shark-border rounded-lg pl-9 pr-4 py-1.5 text-xs text-white outline-none focus:border-shark-accent" />
        </div>
      </header>

      <div className="flex-1 overflow-auto p-6">
        {loading && <LoadingSpinner />}
        {error && <ErrorState message={error} onRetry={() => search(query)} />}
        {!loading && !error && !results.length && (
          <p className="text-sm text-shark-muted">输入关键词搜索历史故障知识。事件关闭后自动入库。</p>
        )}
        <div className="space-y-4 max-w-4xl">
          {results.map(r => (
            <div key={r.id} className="glass rounded-xl p-5 border border-shark-border">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] text-shark-accent border border-shark-accent/20 px-1.5 py-0.5 rounded">{r.source_type}</span>
                <span className="text-sm font-medium text-white">{r.title}</span>
                <span className="ml-auto text-[10px] text-shark-muted">score {r.score?.toFixed(3)}</span>
              </div>
              <p className="text-xs text-shark-muted leading-relaxed whitespace-pre-wrap">{r.content}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
