'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  Rocket, Clock, RotateCcw, AlertTriangle,
  Loader2, WifiOff, Zap,
} from 'lucide-react'
import { cn, fmtTime } from '@/lib/utils'

const API = ''

interface Deployment {
  id: string
  service: string
  project: string
  version: string
  previousVersion: string
  status: string
  buildStatus: string
  buildDurationSec: number
  isLatest: boolean
  triggeredBy: string
  triggeredByUser: string
  commitMessage: string
  ciJobUrl: string
  startedAt: string | null
  completedAt: string | null
  failureKind?: string
}

interface DeploymentDetail extends Deployment {
  stages: { stage: string; status: string; detail?: string; duration_sec?: number }[]
  failureReason: string
}

function fmtDuration(sec: number) {
  if (!sec) return '—'
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return s ? `${m}m ${s}s` : `${m}m`
}

export default function DeploymentsPage() {
  const [services, setServices] = useState<Deployment[]>([])
  const [detail, setDetail] = useState<DeploymentDetail | null>(null)
  const [selectedService, setSelectedService] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rollingBack, setRollingBack] = useState(false)
  const [autoRollback, setAutoRollback] = useState<boolean | null>(null)
  const [savingRollback, setSavingRollback] = useState(false)

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/deployments/config`)
      if (res.ok) {
        const data = await res.json()
        setAutoRollback(Boolean(data.autoRollback))
      }
    } catch {}
  }, [])

  const toggleAutoRollback = async () => {
    if (autoRollback === null || savingRollback) return
    setSavingRollback(true)
    const next = !autoRollback
    try {
      const res = await fetch(`${API}/api/deployments/config`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ auto_rollback: next }),
      })
      if (res.ok) {
        const data = await res.json()
        setAutoRollback(Boolean(data.autoRollback))
      }
    } catch {} finally { setSavingRollback(false) }
  }

  const fetchLatest = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/deployments`)
      if (!res.ok) throw new Error('API error')
      const data = await res.json()
      setServices(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : '无法连接 API')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchLatest(); fetchConfig() }, [fetchLatest, fetchConfig])

  const selectService = async (svc: string, preferId?: string) => {
    setSelectedService(svc)
    const id = preferId || services.find(d => d.service === svc)?.id
    if (!id) {
      setDetail(null)
      setSelectedId(null)
      return
    }
    setSelectedId(id)
    try {
      const dRes = await fetch(`${API}/api/deployments/${id}`)
      setDetail(await dRes.json())
    } catch {
      setDetail(null)
    }
  }

  const doRollback = async () => {
    if (!selectedId || !selectedService) return
    setRollingBack(true)
    try {
      await fetch(`${API}/api/deployments/${selectedId}/rollback`, { method: 'POST' })
      await selectService(selectedService, selectedId)
      fetchLatest()
    } catch {} finally { setRollingBack(false) }
  }

  if (error && services.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-3">
          <WifiOff size={40} className="text-red-400 mx-auto" />
          <p className="text-sm text-shark-muted">{error}</p>
          <button onClick={fetchLatest} className="text-xs text-shark-accent border border-shark-accent/30 px-3 py-1.5 rounded">重试</button>
        </div>
      </div>
    )
  }

  if (loading) return <div className="h-full flex items-center justify-center"><Loader2 size={32} className="animate-spin text-shark-accent" /></div>

  const dep = detail || services.find(d => d.id === selectedId)
  const failureLabel = (dep?.failureKind || detail?.failureKind) === 'startup' ? 'Pod 启动日志' : '构建日志'

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2">
          <Rocket size={16} className="text-emerald-400" /> 发布管理
        </h1>
        <span className="ml-3 text-xs text-shark-muted">build · 每服务最新一条</span>
        {autoRollback !== null && (
          <button
            onClick={toggleAutoRollback}
            disabled={savingRollback}
            title="构建失败时是否自动 ArgoCD 回滚"
            className={cn(
              'ml-4 flex items-center gap-1.5 text-xs px-2.5 py-1 rounded border transition-colors disabled:opacity-50',
              autoRollback
                ? 'text-emerald-400 border-emerald-400/30 bg-emerald-400/5'
                : 'text-shark-muted border-shark-border hover:text-white',
            )}
          >
            <RotateCcw size={12} />
            {savingRollback ? '保存中…' : autoRollback ? '自动回滚 开' : '自动回滚 关'}
          </button>
        )}
        <button onClick={fetchLatest} className="ml-auto text-xs text-shark-muted hover:text-white">刷新</button>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <div className="w-[300px] border-r border-shark-border overflow-auto">
          <p className="text-[10px] text-shark-muted px-4 py-2 uppercase tracking-wide">服务 · 最新</p>
          {services.length === 0 && <p className="text-xs text-shark-muted p-4">暂无构建记录</p>}
          {services.map(d => (
            <button key={d.id} onClick={() => selectService(d.service, d.id)}
              className={cn('w-full text-left p-4 border-b border-shark-border transition-colors',
                selectedService === d.service ? 'bg-shark-accent/10 border-l-2 border-l-shark-accent' : 'hover:bg-white/[0.02]')}>
              <div className="flex items-center gap-2 mb-1">
                <StatusBadge status={d.buildStatus || d.status} />
                <span className="text-xs font-medium text-white truncate">{d.service}</span>
              </div>
              <div className="flex items-center gap-2 text-[10px] text-shark-muted">
                <Clock size={10} />
                <span>{fmtDuration(d.buildDurationSec)}</span>
                <span className="ml-auto">{d.version?.slice(0, 12)}</span>
              </div>
              <p className="text-[10px] text-shark-muted mt-1 line-clamp-1">{d.project}</p>
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto p-6">
          {!dep && <p className="text-sm text-shark-muted">选择服务查看详情</p>}
          {dep && (
            <>
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <StatusBadge status={dep.buildStatus || dep.status} />
                  <span className="text-lg font-bold text-white">{dep.service}</span>
                  <span className="text-xs text-shark-muted">{dep.project}</span>
                </div>
                <div className="flex flex-wrap gap-4 text-xs text-shark-muted">
                  <span>版本: {dep.version}</span>
                  <span>耗时: {fmtDuration(dep.buildDurationSec)}</span>
                  <span>{dep.triggeredByUser || dep.triggeredBy} · {fmtTime(dep.startedAt || '')}</span>
                </div>
                {dep.commitMessage && <p className="text-xs text-shark-muted mt-2">提交: {dep.commitMessage}</p>}
                {dep.ciJobUrl && (
                  <a href={dep.ciJobUrl} target="_blank" rel="noreferrer"
                    className="text-xs text-shark-accent hover:underline mt-1 inline-block">打开 CI Pipeline →</a>
                )}
                {(dep.buildStatus === 'failed' || dep.status === 'failed' || dep.status === 'rolled_back') && (
                  <button onClick={doRollback} disabled={rollingBack}
                    className="mt-3 flex items-center gap-1 text-xs bg-red-400/10 border border-red-400/30 text-red-400 px-3 py-1.5 rounded hover:bg-red-400/20 disabled:opacity-50">
                    <RotateCcw size={14} /> {rollingBack ? '回滚中...' : '手动回滚 ArgoCD'}
                  </button>
                )}
              </div>

              {(detail?.stages?.length ?? 0) > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <Zap size={14} className="text-amber-400" /> 阶段耗时
                  </h3>
                  <div className="space-y-2">
                    {detail!.stages.map((s, i) => {
                      const maxSec = Math.max(...detail!.stages.map(x => x.duration_sec || 0), 1)
                      const pct = ((s.duration_sec || 0) / maxSec) * 100
                      return (
                        <div key={i} className="flex items-center gap-3 text-xs">
                          <span className="w-28 shrink-0 text-shark-muted truncate">{s.stage}</span>
                          <div className="flex-1 h-2 bg-slate-900 rounded overflow-hidden">
                            <div className={cn('h-full rounded', s.status === 'failed' ? 'bg-red-400' : 'bg-emerald-400/70')}
                              style={{ width: `${Math.max(pct, 4)}%` }} />
                          </div>
                          <span className="w-12 text-right text-white">{s.detail || `${s.duration_sec || 0}s`}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {detail?.failureReason && (
                <div className="p-4 rounded-xl border border-red-400/20 bg-red-400/5">
                  <h3 className="text-sm font-semibold text-red-400 mb-1 flex items-center gap-2">
                    <AlertTriangle size={14} /> {failureLabel}
                  </h3>
                  <pre className="text-[10px] text-shark-muted whitespace-pre-wrap max-h-64 overflow-auto font-mono">
                    {detail.failureReason}
                  </pre>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status, compact }: { status: string; compact?: boolean }) {
  const map: Record<string, { color: string; label: string }> = {
    success: { color: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/5', label: compact ? '✓' : '成功' },
    failed: { color: 'text-red-400 border-red-400/30 bg-red-400/5', label: compact ? '✗' : '失败' },
    canceled: { color: 'text-shark-muted border-shark-border', label: compact ? '—' : '取消' },
    rolled_back: { color: 'text-orange-400 border-orange-400/30 bg-orange-400/5', label: compact ? '↩' : '已回滚' },
    deploying: { color: 'text-amber-400 border-amber-400/30 bg-amber-400/5', label: '部署中' },
  }
  const m = map[status] || { color: 'text-shark-muted border-shark-border', label: status }
  return (
    <span className={cn('px-1.5 py-0.5 rounded font-medium border', compact ? 'text-[9px]' : 'text-[10px]', m.color)}>
      {m.label}
    </span>
  )
}
