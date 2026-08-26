'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Brain, CheckCircle2, AlertTriangle, Zap, FileText, Wrench } from 'lucide-react'
import { cn, severityBadge, fmtTime } from '@/lib/utils'
import { apiJson } from '@/lib/api'
import { ErrorState, LoadingSpinner } from '@/components/ui/AsyncState'
import type { Incident, IncidentDetail, IncidentEvent, AnalysisReport } from '@/lib/types'

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<IncidentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [acting, setActing] = useState(false)

  const fetchList = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiJson<Incident[]>('/api/incidents?limit=50')
      setIncidents(data)
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
    apiJson<IncidentDetail>(`/api/incidents/${selected}`)
      .then(d => { if (!cancelled) setDetail(d) })
      .catch(() => { if (!cancelled) setDetail(null) })
    return () => { cancelled = true }
  }, [selected])

  useEffect(() => {
    if (!selected && incidents.length) setSelected(incidents[0].id)
  }, [incidents, selected])

  const patchStatus = async (status: string) => {
    if (!selected) return
    setActing(true)
    try {
      await apiJson(`/api/incidents/${selected}/status`, {
        method: 'PATCH', body: JSON.stringify({ status, actor: 'user' }),
      })
      await fetchList()
      const d = await apiJson<IncidentDetail>(`/api/incidents/${selected}`)
      setDetail(d)
    } finally {
      setActing(false)
    }
  }

  const diagnose = async () => {
    if (!selected) return
    setActing(true)
    try {
      await apiJson(`/api/incidents/${selected}/diagnose`, { method: 'POST' })
      setTimeout(async () => {
        const d = await apiJson<IncidentDetail>(`/api/incidents/${selected}`)
        setDetail(d)
        fetchList()
        setActing(false)
      }, 3000)
    } catch {
      setActing(false)
    }
  }

  const exportPostmortem = async () => {
    if (!selected) return
    const data = await apiJson<{ markdown: string }>(`/api/incidents/${selected}/postmortem`)
    const blob = new Blob([data.markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `postmortem-${selected.slice(0, 8)}.md`
    a.click()
  }

  if (loading && !incidents.length) return <LoadingSpinner />
  if (error && !incidents.length) return <ErrorState message={error} onRetry={fetchList} />

  const incident = incidents.find(i => i.id === selected)

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <Link href="/" className="mr-3 text-shark-muted hover:text-white"><ArrowLeft size={18} /></Link>
        <h1 className="text-sm font-semibold text-white flex items-center gap-2">
          <AlertTriangle size={16} className="text-red-400" /> 事件中心
        </h1>
        <span className="ml-3 text-xs text-shark-muted">{incidents.length} 个事件</span>
        <button onClick={fetchList} className="ml-auto text-xs text-shark-muted hover:text-white">刷新</button>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <div className="w-[320px] border-r border-shark-border overflow-auto">
          {incidents.map(inc => (
            <button key={inc.id} onClick={() => setSelected(inc.id)}
              className={cn('w-full text-left p-4 border-b border-shark-border transition-colors',
                selected === inc.id ? 'bg-shark-accent/10 border-l-2 border-l-shark-accent' : 'hover:bg-white/[0.02]')}>
              <div className="flex items-center gap-2 mb-1">
                <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium border', severityBadge[inc.severity])}>
                  {inc.severity === 'critical' ? '紧急' : inc.severity === 'warning' ? '警告' : '信息'}
                </span>
                <StatusDot status={inc.status} />
              </div>
              <p className="text-xs font-medium text-white mb-1">{inc.title}</p>
              <p className="text-[10px] text-shark-muted">{inc.affectedServices?.join(', ') || inc.source} · {fmtTime(inc.createdAt)}</p>
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto p-6">
          {!incident && <p className="text-sm text-shark-muted">选择一个事件</p>}
          {incident && (
            <>
              <div className="mb-4 flex flex-wrap gap-2">
                {incident.status === 'firing' && (
                  <ActionBtn onClick={() => patchStatus('acknowledged')} disabled={acting} label="确认" icon={CheckCircle2} />
                )}
                {['firing', 'acknowledged', 'analyzed'].includes(incident.status) && (
                  <ActionBtn onClick={diagnose} disabled={acting || incident.status === 'analyzing'} label="AI 诊断" icon={Brain} accent />
                )}
                {incident.status !== 'resolved' && (
                  <ActionBtn onClick={() => patchStatus('resolved')} disabled={acting} label="关闭" icon={CheckCircle2} />
                )}
                <ActionBtn onClick={exportPostmortem} label="导出 Postmortem" icon={FileText} />
              </div>

              <h2 className="text-lg font-bold text-white mb-2">{incident.title}</h2>
              <p className="text-sm text-shark-muted mb-6">
                影响: {incident.affectedServices?.join(', ') || '—'} · 来源: {incident.source}
              </p>

              {detail?.recentDeployments?.length ? (
                <div className="mb-6 p-4 rounded-xl border border-shark-border bg-slate-900/40">
                  <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2"><Wrench size={14} /> 近期发布</h3>
                  {detail.recentDeployments.map(d => (
                    <div key={d.id} className="text-xs text-shark-muted py-1">
                      {d.service} → {d.version} · {d.status} · {fmtTime(d.startedAt)}
                    </div>
                  ))}
                </div>
              ) : null}

              {detail?.reports?.map((r, i) => (
                <ReportCard key={i} report={r} />
              ))}

              {detail?.timeline?.length ? (
                <>
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <Zap size={16} className="text-amber-400" /> 时间线
                  </h3>
                  <div className="relative pl-6 border-l border-shark-border">
                    {detail.timeline.map((ev, i) => (
                      <TimelineItem key={i} event={ev} />
                    ))}
                  </div>
                </>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function StatusDot({ status }: { status: string }) {
  const label = status === 'firing' ? '待处理' : status === 'analyzing' ? 'AI分析中' : status === 'analyzed' ? '已分析' : status === 'resolved' ? '已解决' : status
  const color = status === 'firing' ? 'text-red-400' : status === 'analyzing' ? 'text-amber-400 animate-pulse' : 'text-shark-muted'
  return <span className={cn('text-[10px]', color)}>● {label}</span>
}

function ActionBtn({ onClick, disabled, label, icon: Icon, accent }: {
  onClick: () => void; disabled?: boolean; label: string
  icon: React.ComponentType<{ size?: number | string }>; accent?: boolean
}) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={cn('flex items-center gap-1.5 px-3 py-1.5 rounded text-xs border disabled:opacity-50',
        accent ? 'border-purple-400/40 text-purple-200 hover:bg-purple-400/10' : 'border-shark-border text-shark-muted hover:text-white')}>
      <Icon size={14} /> {label}
    </button>
  )
}

function ReportCard({ report }: { report: AnalysisReport }) {
  return (
    <div className="mb-6 p-4 rounded-xl glass border border-shark-accent/20">
      <h3 className="text-sm font-semibold text-shark-accent mb-3 flex items-center gap-2">
        <Brain size={16} /> AI 分析 · {report.confidence} 置信度
      </h3>
      <p className="text-sm text-shark-muted mb-2"><span className="text-white font-medium">根因：</span>{report.rootCause}</p>
      {report.recommendation && <p className="text-sm text-emerald-400/80 mb-3"><span className="font-medium">建议：</span>{report.recommendation}</p>}
      {report.evidence?.length ? (
        <ul className="text-xs text-shark-muted list-disc pl-4 mb-3">
          {report.evidence.map((e, i) => <li key={i}>{typeof e === 'string' ? e : JSON.stringify(e)}</li>)}
        </ul>
      ) : null}
      {report.toolCalls?.length ? (
        <details className="text-xs">
          <summary className="text-purple-300 cursor-pointer mb-2">诊断证据链 ({report.toolCalls.length} 步)</summary>
          <div className="space-y-2 max-h-48 overflow-auto">
            {report.toolCalls.map((tc, i) => (
              <div key={i} className="p-2 rounded bg-slate-900/60 border border-shark-border font-mono text-[10px]">
                <div className="text-cyan-300">{tc.tool || (tc as { name?: string }).name}</div>
                <div className="text-shark-muted truncate">{String((tc as { input?: unknown }).input || '').slice(0, 200)}</div>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  )
}

function TimelineItem({ event }: { event: IncidentEvent }) {
  return (
    <div className="relative pb-4">
      <div className="absolute -left-[9px] w-4 h-4 rounded-full border-2 border-shark-bg bg-shark-card" />
      <div className="p-3 rounded-lg border border-shark-border bg-shark-card/50">
        <div className="flex justify-between mb-1">
          <span className="text-[10px] text-shark-accent">{event.actor || event.type}</span>
          <span className="text-[10px] text-shark-muted">{fmtTime(event.at)}</span>
        </div>
        <p className="text-xs text-shark-muted">{event.content}</p>
      </div>
    </div>
  )
}
