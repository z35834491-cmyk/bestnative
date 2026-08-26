'use client'

import { useCallback, useEffect, useState } from 'react'
import { DollarSign, Loader2, RefreshCw, TrendingDown } from 'lucide-react'
import { apiJson } from '@/lib/api'
import { ErrorState, LoadingSpinner } from '@/components/ui/AsyncState'

interface CostData {
  totalMonthlyUsd: number
  serviceCount: number
  services: Array<{
    service: string
    namespace: string
    replicas: number
    monthlyUsd: number
    idleCandidate: boolean
    health: string
  }>
  recommendations: Array<{ type: string; service: string; suggestion: string; priority: string }>
  cached?: boolean
}

export default function CostPage() {
  const [data, setData] = useState<CostData | null>(null)
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await apiJson<CostData>('/api/ops/cost/summary'))
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const analyze = async () => {
    setAnalyzing(true)
    try {
      setData(await apiJson<CostData>('/api/ops/cost/analyze', { method: 'POST' }))
    } catch (e) {
      setError(e instanceof Error ? e.message : '分析失败')
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center justify-between px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2">
          <DollarSign size={16} className="text-yellow-400" /> 成本分析
        </h1>
        <div className="flex gap-2">
          <button onClick={fetchData} className="text-xs text-shark-muted hover:text-white flex items-center gap-1 px-2 py-1">
            <RefreshCw size={12} /> 刷新
          </button>
          <button onClick={analyze} disabled={analyzing}
            className="text-xs bg-shark-accent text-white px-3 py-1.5 rounded-lg flex items-center gap-1 disabled:opacity-50">
            {analyzing ? <Loader2 size={12} className="animate-spin" /> : <TrendingDown size={12} />}
            重新分析
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-6 space-y-6">
        {loading && <LoadingSpinner />}
        {error && <ErrorState message={error} onRetry={fetchData} />}
        {!loading && data && (
          <>
            <div className="glass rounded-xl p-6 border border-shark-border">
              <div className="text-[10px] text-shark-muted uppercase">估算月成本 (USD)</div>
              <div className="text-3xl font-bold text-white mt-1">${data.totalMonthlyUsd?.toFixed(2) ?? '0.00'}</div>
              <div className="text-xs text-shark-muted mt-2">{data.serviceCount} 个服务 · {data.cached ? '缓存结果' : '最新分析'}</div>
            </div>

            {data.recommendations?.length > 0 && (
              <section>
                <h2 className="text-xs font-semibold text-shark-muted uppercase mb-3">降本建议</h2>
                <div className="space-y-2">
                  {data.recommendations.map((r, i) => (
                    <div key={i} className="glass rounded-lg px-4 py-3 border border-shark-border text-xs">
                      <span className="text-shark-accent font-medium">{r.service}</span>
                      <span className="text-shark-muted ml-2">[{r.priority}]</span>
                      <p className="text-shark-muted mt-1">{r.suggestion}</p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <section>
              <h2 className="text-xs font-semibold text-shark-muted uppercase mb-3">服务成本排行</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-shark-muted text-left border-b border-shark-border">
                      <th className="py-2 pr-4">服务</th>
                      <th className="py-2 pr-4">命名空间</th>
                      <th className="py-2 pr-4">副本</th>
                      <th className="py-2 pr-4">月成本</th>
                      <th className="py-2">备注</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.services || []).slice(0, 30).map((s, i) => (
                      <tr key={i} className="border-b border-shark-border/50">
                        <td className="py-2 pr-4 text-white">{s.service}</td>
                        <td className="py-2 pr-4 text-shark-muted">{s.namespace}</td>
                        <td className="py-2 pr-4">{s.replicas}</td>
                        <td className="py-2 pr-4">${s.monthlyUsd}</td>
                        <td className="py-2 text-amber-400/80">{s.idleCandidate ? '可缩容' : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
