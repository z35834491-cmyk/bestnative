'use client'

import { useCallback, useEffect, useState } from 'react'
import { Rocket, GitBranch, Clock, CheckCircle2, XCircle, RotateCcw, AlertTriangle, ChevronRight, Loader2, WifiOff } from 'lucide-react'
import { cn, fmtTime } from '@/lib/utils'

const API = ''

interface Deployment {
  id: string; service: string; version: string; previousVersion: string
  status: string; triggeredBy: string; triggeredByUser: string
  commitMessage: string; ciJobUrl: string
  startedAt: string | null; completedAt: string | null
  stages?: { stage: string; status: string; detail?: string }[]
}

interface DeploymentDetail extends Deployment {
  stages: { stage: string; status: string; detail?: string }[]
  metrics: Record<string, unknown>
  failureReason: string
  aiAnalysis: string
}

export default function DeploymentsPage() {
  const [deployments, setDeployments] = useState<Deployment[]>([])
  const [detail, setDetail] = useState<DeploymentDetail | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rollingBack, setRollingBack] = useState(false)

  const fetchList = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/deployments?limit=50`)
      if (!res.ok) throw new Error('API error')
      const data = await res.json()
      setDeployments(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : '无法连接 API')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchList() }, [fetchList])

  useEffect(() => {
    if (!selected) return
    let cancelled = false
    fetch(`${API}/api/deployments/${selected}`)
      .then(r => r.json()).then(d => { if (!cancelled) setDetail(d) }).catch(() => {})
    return () => { cancelled = true }
  }, [selected])

  const doRollback = async () => {
    if (!selected) return
    setRollingBack(true)
    try {
      await fetch(`${API}/api/deployments/${selected}/rollback`, { method: 'POST' })
      fetchList()
    } catch {} finally { setRollingBack(false) }
  }

  if (error && deployments.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-3">
          <WifiOff size={40} className="text-red-400 mx-auto" />
          <p className="text-sm text-shark-muted">{error}</p>
          <button onClick={fetchList} className="text-xs text-shark-accent border border-shark-accent/30 px-3 py-1.5 rounded">重试</button>
        </div>
      </div>
    )
  }

  if (loading) return <div className="h-full flex items-center justify-center"><Loader2 size={32} className="animate-spin text-shark-accent" /></div>

  const dep = deployments.find(d => d.id === selected)

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2"><Rocket size={16} className="text-emerald-400" /> 发布管理</h1>
        <span className="ml-3 text-xs text-shark-muted">{deployments.length} 条记录</span>
        <button onClick={fetchList} className="ml-auto text-xs text-shark-muted hover:text-white">刷新</button>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <div className="w-[360px] border-r border-shark-border overflow-auto">
          {deployments.length === 0 && <p className="text-xs text-shark-muted p-4">暂无发布记录</p>}
          {deployments.map((d) => (
            <button key={d.id} onClick={() => setSelected(d.id)}
              className={cn('w-full text-left p-4 border-b border-shark-border transition-colors',
                selected === d.id ? 'bg-shark-accent/10 border-l-2 border-l-shark-accent' : 'hover:bg-white/[0.02]')}>
              <div className="flex items-center gap-2 mb-1">
                <StatusBadge status={d.status} />
                <span className="text-xs font-medium text-white">{d.service}</span>
                <span className="text-[10px] text-shark-muted ml-auto">{d.version}</span>
              </div>
              <p className="text-[10px] text-shark-muted line-clamp-1">{d.commitMessage || '—'}</p>
              <p className="text-[10px] text-shark-muted mt-1">{d.triggeredBy} · {fmtTime(d.completedAt || d.startedAt || '')}</p>
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto p-6">
          {!dep && <p className="text-sm text-shark-muted">选择一条发布记录查看详情</p>}
          {dep && (
            <>
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-2">
                  <StatusBadge status={dep.status} />
                  <span className="text-lg font-bold text-white">{dep.service}</span>
                  <span className="text-xs text-shark-muted">{dep.previousVersion || '—'} → {dep.version}</span>
                </div>
                <p className="text-xs text-shark-muted">触发: {dep.triggeredByUser || dep.triggeredBy} · {fmtTime(dep.startedAt || '')}</p>
                {dep.commitMessage && <p className="text-xs text-shark-muted mt-1">提交: {dep.commitMessage}</p>}
                {dep.status === 'failed' && (
                  <button onClick={doRollback} disabled={rollingBack}
                    className="mt-3 flex items-center gap-1 text-xs bg-red-400/10 border border-red-400/30 text-red-400 px-3 py-1.5 rounded hover:bg-red-400/20 transition-colors disabled:opacity-50">
                    <RotateCcw size={14} /> {rollingBack ? '回滚中...' : '回滚到此版本'}
                  </button>
                )}
              </div>

              {/* Stages */}
              {(detail?.stages?.length ?? 0) > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-white mb-3">发布流程</h3>
                  <div className="flex items-center gap-2">
                    {(detail?.stages || dep.stages || []).map((s: { stage: string; status: string; detail?: string }, i: number) => (
                      <div key={i} className="flex items-center gap-2">
                        <div className={cn(
                          'px-3 py-2 rounded-lg border text-xs text-center min-w-[90px]',
                          s.status === 'done' ? 'border-emerald-400/30 bg-emerald-400/5 text-emerald-400' :
                          s.status === 'failed' ? 'border-red-400/30 bg-red-400/5 text-red-400' :
                          'border-shark-border bg-shark-card/50 text-shark-muted'
                        )}>
                          <div className="font-medium">{stageLabel(s.stage)}</div>
                          <div className="text-[10px] mt-0.5">{s.status === 'done' ? '✓' : s.status === 'failed' ? '✗' : '—'}</div>
                        </div>
                        {i < ((detail?.stages || dep.stages || []) as { stage: string; status: string }[]).length - 1 && <ChevronRight size={14} className="text-shark-border" />}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Metrics */}
              {detail?.metrics && Object.keys(detail.metrics).length > 0 && (
                <div className="mb-6 p-4 rounded-xl glass">
                  <h3 className="text-sm font-semibold text-white mb-2">验证指标</h3>
                  <div className="grid grid-cols-3 gap-3 text-xs">
                    {Object.entries(detail.metrics).filter(([k]) => k !== 'healthy' && k !== 'reason').map(([k, v]) => (
                      <div key={k} className="p-2 rounded bg-shark-bg/50 border border-shark-border">
                        <span className="text-shark-muted">{k}</span>
                        <p className="text-white font-medium mt-0.5">{typeof v === 'number' ? v.toFixed(4) : String(v)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Analysis */}
              {detail?.aiAnalysis && (
                <div className="mb-6 p-4 rounded-xl glass border border-shark-accent/20">
                  <h3 className="text-sm font-semibold text-shark-accent mb-2 flex items-center gap-2"><AlertTriangle size={16} /> AI 分析</h3>
                  <p className="text-xs text-shark-muted leading-relaxed">{detail.aiAnalysis}</p>
                </div>
              )}

              {detail?.failureReason && (
                <div className="p-4 rounded-xl border border-red-400/20 bg-red-400/5">
                  <h3 className="text-sm font-semibold text-red-400 mb-1">失败原因</h3>
                  <p className="text-xs text-shark-muted">{detail.failureReason}</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { color: string; label: string }> = {
    success: { color: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/5', label: '✓ 成功' },
    failed: { color: 'text-red-400 border-red-400/30 bg-red-400/5', label: '✗ 失败' },
    deploying: { color: 'text-amber-400 border-amber-400/30 bg-amber-400/5 animate-pulse', label: '部署中' },
    verifying: { color: 'text-blue-400 border-blue-400/30 bg-blue-400/5 animate-pulse', label: '验证中' },
    rolled_back: { color: 'text-orange-400 border-orange-400/30 bg-orange-400/5', label: '已回滚' },
  }
  const m = map[status] || { color: 'text-shark-muted border-shark-border', label: status }
  return <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium border', m.color)}>{m.label}</span>
}

function stageLabel(s: string): string {
  const m: Record<string, string> = { risk_assessment: '风险评估', deploy: '部署', verify: '验证', decision: '决策', rollback: '回滚' }
  return m[s] || s
}
