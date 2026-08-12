'use client'

import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, Brain, Wrench, Search, Zap, CheckCircle2, AlertTriangle, ChevronDown, Loader2, WifiOff } from 'lucide-react'
import Link from 'next/link'
import { cn, severityBadge, fmtTime } from '@/lib/utils'
import type { Incident, IncidentDetail, IncidentEvent, AnalysisReport } from '@/lib/types'

const API = ''

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<IncidentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchList = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/api/incidents?limit=50`)
      if (!res.ok) throw new Error('API error')
      const data = await res.json()
      if (!Array.isArray(data)) throw new Error('Unexpected response')
      setIncidents(data)
      if (!selected && data.length > 0) setSelected(data[0].id)
    } catch (e) {
      setError(e instanceof Error ? e.message : '无法连接 API')
    } finally {
      setLoading(false)
    }
  }, [selected])

  useEffect(() => { fetchList() }, [fetchList])

  // Fetch detail when selected changes
  useEffect(() => {
    if (!selected) return
    let cancelled = false
    fetch(`${API}/api/incidents/${selected}`)
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setDetail(d) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [selected])

  if (error && incidents.length === 0) {
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

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 size={32} className="animate-spin text-shark-accent" />
      </div>
    )
  }

  const incident = incidents.find((i) => i.id === selected)

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <Link href="/" className="mr-3 text-shark-muted hover:text-white transition-colors">
          <ArrowLeft size={18} />
        </Link>
        <h1 className="text-sm font-semibold text-white flex items-center gap-2">
          <AlertTriangle size={16} className="text-red-400" /> 事件中心
        </h1>
        <span className="ml-3 text-xs text-shark-muted">{incidents.length} 个事件</span>
        <button onClick={fetchList} className="ml-auto text-xs text-shark-muted hover:text-white">刷新</button>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <div className="w-[320px] border-r border-shark-border overflow-auto">
          {incidents.length === 0 && (
            <p className="text-xs text-shark-muted p-4">暂无事件</p>
          )}
          {incidents.map((inc) => (
            <button
              key={inc.id}
              onClick={() => setSelected(inc.id)}
              className={cn(
                'w-full text-left p-4 border-b border-shark-border transition-colors',
                selected === inc.id ? 'bg-shark-accent/10 border-l-2 border-l-shark-accent' : 'hover:bg-white/[0.02]'
              )}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium border', severityBadge[inc.severity])}>
                  {inc.severity === 'critical' ? '紧急' : inc.severity === 'warning' ? '警告' : '信息'}
                </span>
                <span className={cn(
                  'text-[10px]',
                  inc.status === 'firing' ? 'text-red-400' :
                  inc.status === 'analyzing' ? 'text-amber-400 animate-pulse' :
                  inc.status === 'analyzed' ? 'text-emerald-400' : 'text-shark-muted'
                )}>
                  {inc.status === 'firing' ? '● 待处理' :
                   inc.status === 'acknowledged' ? '● 已确认' :
                   inc.status === 'analyzing' ? '● AI 分析中' :
                   inc.status === 'analyzed' ? '● 已分析' : '● 已解决'}
                </span>
              </div>
              <p className="text-xs font-medium text-white mb-1">{inc.title}</p>
              <p className="text-[10px] text-shark-muted">
                {inc.affectedServices?.join(', ') || inc.source} · {fmtTime(inc.createdAt)}
              </p>
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto p-6">
          {!incident && <p className="text-sm text-shark-muted">选择一个事件查看详情</p>}

          {incident && (
            <>
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-2">
                  <span className={cn('px-2 py-0.5 rounded text-[10px] font-medium border', severityBadge[incident.severity])}>
                    {incident.severity === 'critical' ? '紧急' : incident.severity === 'warning' ? '警告' : '信息'}
                  </span>
                  <span className="text-xs text-shark-muted truncate">ID: {incident.id}</span>
                  <span className="text-xs text-shark-muted ml-auto">{fmtTime(incident.createdAt)}</span>
                </div>
                <h2 className="text-lg font-bold text-white mb-2">{incident.title}</h2>
                <p className="text-sm text-shark-muted">
                  影响: {incident.affectedServices?.join(', ') || '—'} · 来源: {incident.source} · 处理人: {incident.assignee || '未分配'}
                </p>
              </div>

              {/* AI Reports */}
              {detail?.reports?.length ? detail.reports.map((r, i) => (
                <div key={i} className="mb-6 p-4 rounded-xl glass border border-shark-accent/20">
                  <h3 className="text-sm font-semibold text-shark-accent mb-3 flex items-center gap-2">
                    <Brain size={16} /> AI 分析结果
                    <span className="ml-auto text-xs text-emerald-400">{r.confidence} 置信度</span>
                  </h3>
                  <p className="text-sm text-shark-muted leading-relaxed mb-3">
                    <span className="text-white font-medium">根因：</span>{r.rootCause}
                  </p>
                  {r.recommendation && (
                    <p className="text-sm text-emerald-400/80 leading-relaxed">
                      <span className="font-medium">建议：</span>{r.recommendation}
                    </p>
                  )}
                  <p className="text-[10px] text-shark-muted mt-2">Token: {r.tokens} · 可自动修复: {r.canAutoFix ? '✅' : '❌'}</p>
                </div>
              )) : (incident.status === 'analyzed' && (
                <p className="text-xs text-shark-muted mb-4">分析报告加载中...</p>
              ))}

              {/* Timeline */}
              {detail?.timeline?.length ? (
                <>
                  <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                    <Zap size={16} className="text-amber-400" /> Agent 执行记录
                  </h3>
                  <div className="relative pl-6 border-l border-shark-border">
                    {detail.timeline.map((ev, i) => (
                      <TimelineItem key={i} event={ev} />
                    ))}
                  </div>
                </>
              ) : (
                <p className="text-xs text-shark-muted">暂无执行记录{incident.status === 'firing' ? '（请触发诊断）' : ''}</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function TimelineItem({ event }: { event: IncidentEvent }) {
  return (
    <div className="relative pb-4">
      <div className="absolute -left-[9px] w-4 h-4 rounded-full border-2 border-shark-bg bg-shark-card flex items-center justify-center">
        <div className="w-1.5 h-1.5 rounded-full bg-shark-accent" />
      </div>
      <div className="p-3 rounded-lg border border-shark-border bg-shark-card/50">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] text-shark-accent font-medium">{event.actor || event.type}</span>
          <span className="text-[10px] text-shark-muted">{fmtTime(event.at)}</span>
        </div>
        <p className="text-xs text-shark-muted leading-relaxed">{event.content}</p>
      </div>
    </div>
  )
}
