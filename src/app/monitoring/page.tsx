'use client'

import { useCallback, useEffect, useState } from 'react'
import { Activity, AlertTriangle, Loader2, Play, RefreshCw } from 'lucide-react'
import { apiJson } from '@/lib/api'
import { ErrorState, LoadingSpinner } from '@/components/ui/AsyncState'
import { cn } from '@/lib/utils'

interface PatrolSummary {
  serviceCount: number
  healthSummary: Record<string, number>
  latestPatrol: { output?: { issues?: Issue[]; summary?: Record<string, number>; prometheusConnected?: boolean } } | null
}

interface Issue {
  service: string
  namespace: string
  health: string
  problem: string
  replicas: string
}

export default function MonitoringPage() {
  const [data, setData] = useState<PatrolSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [patrolling, setPatrolling] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await apiJson<PatrolSummary>('/api/ops/monitor/summary'))
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const runPatrol = async () => {
    setPatrolling(true)
    try {
      await apiJson('/api/ops/monitor/patrol', { method: 'POST' })
      await fetchData()
    } catch (e) {
      setError(e instanceof Error ? e.message : '巡检失败')
    } finally {
      setPatrolling(false)
    }
  }

  const issues = data?.latestPatrol?.output?.issues || []
  const summary = data?.healthSummary || {}

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center justify-between px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2">
          <Activity size={16} className="text-emerald-400" /> 监控巡检
        </h1>
        <div className="flex gap-2">
          <button onClick={fetchData} className="text-xs text-shark-muted hover:text-white flex items-center gap-1 px-2 py-1">
            <RefreshCw size={12} /> 刷新
          </button>
          <button onClick={runPatrol} disabled={patrolling}
            className="text-xs bg-shark-accent text-white px-3 py-1.5 rounded-lg flex items-center gap-1 disabled:opacity-50">
            {patrolling ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            立即巡检
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-6 space-y-6">
        {loading && <LoadingSpinner />}
        {error && <ErrorState message={error} onRetry={fetchData} />}
        {!loading && data && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[
                ['healthy', '健康', 'text-emerald-400'],
                ['degraded', '降级', 'text-amber-400'],
                ['critical', '严重', 'text-red-400'],
                ['unknown', '未知', 'text-shark-muted'],
                ['total', '服务总数', 'text-white'],
              ].map(([key, label, color]) => (
                <div key={key} className="glass rounded-xl p-4 border border-shark-border">
                  <div className="text-[10px] text-shark-muted uppercase">{label}</div>
                  <div className={cn('text-2xl font-bold mt-1', color)}>
                    {key === 'total' ? data.serviceCount : (summary[key] || 0)}
                  </div>
                </div>
              ))}
            </div>

            {data.latestPatrol?.output?.prometheusConnected === false && (
              <p className="text-xs text-amber-400/90">Prometheus 未连通，指标巡检受限（可在 .env 配 PROMETHEUS_URL）</p>
            )}

            <section>
              <h2 className="text-xs font-semibold text-shark-muted uppercase mb-3 flex items-center gap-1">
                <AlertTriangle size={12} /> 巡检问题 ({issues.length})
              </h2>
              {issues.length === 0 ? (
                <p className="text-sm text-shark-muted">最近一次巡检未发现异常服务。</p>
              ) : (
                <div className="space-y-2">
                  {issues.map((i, idx) => (
                    <div key={idx} className="glass rounded-lg px-4 py-3 border border-shark-border flex items-center gap-4 text-xs">
                      <span className={cn('font-mono', i.health === 'critical' ? 'text-red-400' : 'text-amber-400')}>
                        {i.namespace}/{i.service}
                      </span>
                      <span className="text-shark-muted flex-1">{i.problem}</span>
                      <span className="text-shark-muted">{i.replicas}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
