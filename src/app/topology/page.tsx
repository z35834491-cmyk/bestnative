'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Activity, AlertTriangle, Database, GitFork, Loader2, Search, WifiOff, X, Zap, ZoomIn, ZoomOut } from 'lucide-react'
import { cn, healthDot } from '@/lib/utils'
import type { TopoEdge, TopoNode, TraceGraph, TraceSummary, TraceTimeline } from '@/lib/types'

const API = ''

export default function TopologyPage() {
  const [graph, setGraph] = useState<TraceGraph | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<TopoEdge | null>(null)
  const [scale, setScale] = useState(1)
  const [service, setService] = useState('exchange-gateway')
  const [hours, setHours] = useState(24)
  const [timeline, setTimeline] = useState<TraceTimeline | null>(null)
  const [timelineLoading, setTimelineLoading] = useState(false)

  const fetchGraph = useCallback(async () => {
    setLoading(true); setError(null); setSelectedEdge(null); setTimeline(null)
    try {
      const res = await fetch(`${API}/api/topology/trace-graph?service=${encodeURIComponent(service)}&hours=${hours}&trace_limit=200`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || data.error || 'API error')
      setGraph(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : '无法连接 API')
    } finally {
      setLoading(false)
    }
  }, [service, hours])

  useEffect(() => { fetchGraph() }, [fetchGraph])

  const openTrace = async (traceId: string) => {
    setTimelineLoading(true)
    try {
      const res = await fetch(`${API}/api/topology/traces/${encodeURIComponent(traceId)}?size=800`)
      setTimeline(await res.json())
    } finally {
      setTimelineLoading(false)
    }
  }

  if (error) {
    return <div className="h-full flex items-center justify-center"><div className="text-center space-y-3"><WifiOff size={40} className="text-red-400 mx-auto" /><p className="text-sm text-shark-muted">{error}</p><button onClick={fetchGraph} className="text-xs text-shark-accent border border-shark-accent/30 px-3 py-1.5 rounded">重试</button></div></div>
  }

  const nodes = layoutNodes(graph?.nodes || [])
  const edges = graph?.edges || []
  const traces = graph?.traces || []
  const serviceOptions = useMemo(() => [...new Set([service, ...nodes.filter(n => n.type === 'service').map(n => n.name), ...traces.flatMap(t => t.services)])].filter(Boolean).sort(), [nodes, traces, service])
  const middlewareCount = nodes.filter(n => n.type === 'middleware').length
  const delayedEdges = edges.filter(e => e.avgLatencyMs !== undefined || e.p95LatencyMs !== undefined).length
  const maxX = Math.max(...nodes.map(n => (n.x || 0) + 150), 900) + 40
  const maxY = Math.max(...nodes.map(n => (n.y || 0) + 72), 520) + 40

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14 gap-3">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2"><GitFork size={16} className="text-purple-400" /> 服务拓扑</h1>
        <span className="text-xs text-shark-muted">Trace 链路 · {nodes.length} 节点 · {edges.length} 连接 · {traces.length} traces · 中间件 {middlewareCount} · 延迟边 {delayedEdges}</span>
        <div className="flex items-center gap-2 ml-2">
          <Search size={14} className="text-shark-muted" />
          <input value={service} onChange={e => setService(e.target.value)} list="trace-service-options" placeholder="入口服务" className="bg-slate-950/70 border border-shark-border rounded px-2 py-1 text-xs text-white w-44" />
          <datalist id="trace-service-options">{serviceOptions.map(s => <option value={s} key={s} />)}</datalist>
          <select value={hours} onChange={e => setHours(Number(e.target.value))} className="bg-slate-950/70 border border-shark-border rounded px-2 py-1 text-xs text-white">
            <option value={1}>1小时</option><option value={6}>6小时</option><option value={24}>24小时</option><option value={72}>3天</option><option value={168}>7天</option>
          </select>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => setScale(s => Math.max(0.3, s - 0.15))} className="text-shark-muted hover:text-white"><ZoomOut size={16} /></button>
          <span className="text-xs text-shark-muted">{Math.round(scale * 100)}%</span>
          <button onClick={() => setScale(s => Math.min(2, s + 0.15))} className="text-shark-muted hover:text-white"><ZoomIn size={16} /></button>
          <button onClick={fetchGraph} className="text-xs text-shark-muted hover:text-white ml-2">刷新</button>
        </div>
      </header>

      <div className="flex-1 min-h-0 flex">
        <div className="flex-1 overflow-auto relative">
          {loading ? <div className="h-full flex items-center justify-center"><Loader2 size={32} className="animate-spin text-shark-accent" /></div> : nodes.length === 0 ? (
            <div className="h-full flex items-center justify-center"><p className="text-sm text-shark-muted">ES trace_log 当前筛选条件无链路</p></div>
          ) : (
            <svg viewBox={`0 0 ${maxX} ${maxY}`} className="min-w-full min-h-full" style={{ transform: `scale(${scale})`, transformOrigin: '0 0' }}>
              {edges.map((e, i) => {
                const fromId = e.from || e.source || ''
                const toId = e.to || e.target || ''
                const from = nodes.find(s => s.id === fromId || s.name === fromId)
                const to = nodes.find(s => s.id === toId || s.name === toId)
                if (!from || !to) return null
                const col = edgeColor(e, to)
                const active = selectedEdge === e
                const label = edgeLabel(e)
                return (
                  <g key={`${fromId}-${toId}-${i}`} onClick={() => setSelectedEdge(e)} className="cursor-pointer">
                    <line x1={(from.x||0)+70} y1={(from.y||0)+34} x2={(to.x||0)+70} y2={(to.y||0)+34} stroke={col} strokeWidth={active ? 4 : 2.4} opacity={active ? 0.95 : 0.65} />
                    <polygon points={`${(to.x||0)+70},${(to.y||0)+34} ${(to.x||0)+64},${(to.y||0)+29} ${(to.x||0)+64},${(to.y||0)+39}`} fill={col} opacity={0.75} />
                    <text x={((from.x||0)+(to.x||0))/2+70} y={((from.y||0)+(to.y||0))/2+24} textAnchor="middle" className="text-[10px] fill-purple-200">{label}</text>
                  </g>
                )
              })}
              {nodes.map(svc => {
                const sel = selected === svc.id
                const x = svc.x || 0; const y = svc.y || 0
                const isMid = svc.type === 'middleware'
                return (
                  <g key={svc.id} transform={`translate(${x},${y})`} onClick={() => setSelected(sel ? null : svc.id)} className="cursor-pointer">
                    <rect width="140" height="68" rx={isMid ? 18 : 10} fill={sel ? 'rgba(56,189,248,0.12)' : '#0f172a'} stroke={sel ? '#38bdf8' : isMid ? '#0ea5e9' : '#581c87'} strokeWidth={sel ? 2 : 1.2} />
                    <circle cx="14" cy="14" r="5" className={healthDot[svc.health]} />
                    <text x="26" y="18" className="text-[9px] fill-shark-muted uppercase">{isMid ? 'middleware' : 'trace service'}</text>
                    <text x="70" y="38" textAnchor="middle" className={cn('text-[11px] font-semibold', isMid ? 'fill-cyan-200' : 'fill-white')}>
                      {svc.name.length > 20 ? svc.name.slice(0,18)+'…' : svc.name}
                    </text>
                    <text x="70" y="56" textAnchor="middle" className="text-[9px] fill-shark-muted">{svc.traceCount || 0} traces · {svc.errorCount || 0} err</text>
                  </g>
                )
              })}
            </svg>
          )}
        </div>
        <TracePanel traces={traces} edge={selectedEdge} timeline={timeline} loading={timelineLoading} onOpenTrace={openTrace} onCloseTimeline={() => setTimeline(null)} />
      </div>
    </div>
  )
}

function edgeLabel(e: TopoEdge) {
  const latency = e.p95LatencyMs ?? e.avgLatencyMs
  const latencyText = latency !== undefined ? `${latency}ms` : '无耗时'
  return `${e.traceCount || 1} traces · ${latencyText}`
}

function edgeColor(e: TopoEdge, target: TopoNode) {
  if (e.health === 'critical') return '#ef4444'
  if (e.health === 'degraded') return '#f59e0b'
  if (target.type === 'middleware') return '#06b6d4'
  return '#a855f7'
}

function TracePanel({ traces, edge, timeline, loading, onOpenTrace, onCloseTimeline }: { traces: TraceSummary[]; edge: TopoEdge | null; timeline: TraceTimeline | null; loading: boolean; onOpenTrace: (id: string) => void; onCloseTimeline: () => void }) {
  const edgeTrace = edge?.lastTraceId
  const filtered = edge ? traces.filter(t => {
    const from = edge.from || edge.source || ''
    const to = edge.to || edge.target || ''
    return t.services.includes(from) || t.services.includes(to) || t.components?.some(c => to.endsWith(c))
  }) : traces
  return (
    <aside className="w-[430px] shrink-0 border-l border-shark-border bg-slate-950/60 overflow-hidden flex flex-col">
      <div className="p-4 border-b border-shark-border">
        <div className="text-sm font-semibold text-white flex items-center gap-2"><Activity size={15} className="text-purple-300" /> Trace 链路详情</div>
        {edge ? <div className="mt-2 text-xs text-shark-muted space-y-1">
          <div>选中边：<span className="text-white">{edge.from || edge.source}</span> → <span className="text-white">{edge.to || edge.target}</span></div>
          <div>调用 {edge.traceCount || 0} 次 · 错误 {edge.errorCount || 0} 次</div>
          <div>平均延迟：<span className="text-cyan-200">{edge.avgLatencyMs ?? '无数据'} ms</span> · P95：<span className="text-cyan-200">{edge.p95LatencyMs ?? '无数据'} ms</span> · 样本 {edge.latencySamples || 0}</div>
        </div> : <div className="mt-2 text-xs text-shark-muted">点击图上的连线查看调用次数、错误数、平均/P95 延迟；点击 traceId 查看完整日志时间线。</div>}
        {edgeTrace && <button onClick={() => onOpenTrace(edgeTrace)} className="mt-3 text-xs px-3 py-1.5 rounded border border-purple-400/30 text-purple-200 hover:bg-purple-400/10">打开最近 trace</button>}
      </div>
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {filtered.slice(0, 80).map(t => <button key={t.traceId} onClick={() => onOpenTrace(t.traceId)} className="w-full text-left rounded-lg border border-shark-border bg-slate-900/60 hover:border-purple-400/40 p-3">
          <div className="flex items-center gap-2"><code className="text-[11px] text-purple-200 truncate flex-1">{t.traceId}</code>{t.hasError && <AlertTriangle size={13} className="text-yellow-300" />}</div>
          <div className="mt-1 text-[11px] text-shark-muted truncate">{t.services.join(' → ') || 'unknown'}{t.components?.length ? ` → ${t.components.map(c => c.toUpperCase()).join(' / ')}` : ''}</div>
          <div className="mt-1 text-[10px] text-shark-muted">{t.eventCount} logs · 最大耗时 {t.maxDurationMs ?? '无'} ms · {t.lastSeen || ''}</div>
        </button>)}
      </div>
      {timeline && <div className="absolute right-0 top-14 bottom-0 w-[640px] bg-slate-950 border-l border-purple-400/30 shadow-2xl flex flex-col z-20">
        <div className="p-4 border-b border-shark-border flex items-start gap-3"><div className="flex-1"><div className="text-sm font-semibold text-white">Trace 时间线</div><code className="text-xs text-purple-200 break-all">{timeline.traceId}</code><div className="text-xs text-shark-muted mt-1">{timeline.services.join(' → ')} · {timeline.eventCount} logs</div></div><button onClick={onCloseTimeline} className="text-shark-muted hover:text-white"><X size={18} /></button></div>
        <div className="flex-1 overflow-auto p-4 space-y-3">
          {loading ? <Loader2 className="animate-spin text-purple-300" /> : timeline.events.map((e, i) => <div key={`${e.spanId}-${i}`} className={cn('border-l-2 pl-3 py-1', e.component ? 'border-cyan-400/60' : 'border-purple-500/50')}>
            <div className="text-[11px] text-shark-muted flex items-center gap-2 flex-wrap"><span className="text-purple-200">{e.timestamp}</span><span className="text-white">{e.serviceName}</span><span>{e.podName}</span>{e.component && <span className="inline-flex items-center gap-1 rounded bg-cyan-500/10 px-1.5 py-0.5 text-cyan-200"><Database size={10} />{e.component.toUpperCase()}</span>}{e.durationMs !== undefined && e.durationMs !== null && <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.5 text-amber-200"><Zap size={10} />{e.durationMs}ms</span>}</div>
            <pre className={cn('mt-1 text-xs font-mono whitespace-pre-wrap leading-5', e.logLevel === 'ERROR' ? 'text-red-300' : e.logLevel === 'WARN' ? 'text-yellow-300' : 'text-slate-300')}>{e.logLevel} | {e.javaModule} | {e.logMessage}</pre>
          </div>)}
        </div>
      </div>}
    </aside>
  )
}

function layoutNodes(nodes: TopoNode[]): TopoNode[] {
  const serviceNodes = nodes.filter(n => n.type === 'service')
  const middlewareNodes = nodes.filter(n => n.type === 'middleware')
  const W = 150; const H = 78; const GX = 28; const GY = 26; const COLS = 5
  const layoutGroup = (group: TopoNode[], startY: number) => group.map((n, i) => ({ ...n, x: 10 + (i % COLS) * (W + GX), y: startY + Math.floor(i / COLS) * (H + GY) }))
  const services = layoutGroup(serviceNodes, 10)
  const serviceRows = Math.max(1, Math.ceil(serviceNodes.length / COLS))
  const middlewares = layoutGroup(middlewareNodes, 10 + serviceRows * (H + GY) + 40)
  return [...services, ...middlewares]
}
