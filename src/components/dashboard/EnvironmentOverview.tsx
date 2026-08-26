'use client'

import Link from 'next/link'
import { useMemo, useState } from 'react'
import { AlertTriangle, GitFork, Server, Shield } from 'lucide-react'
import { cn, healthDot, fmtTime, severityBadge } from '@/lib/utils'
import { layoutNodes, graphBounds } from '@/lib/topology-layout'
import type { ClusterInfo, Incident, TopoEdge, TopoNode, TopologyGraph, TraceGraph } from '@/lib/types'

interface EnvironmentOverviewProps {
  k8sGraph: TopologyGraph | null
  traceGraph: TraceGraph | null
  clusters: ClusterInfo[]
  incidents: Incident[]
  environment?: string
}

function healthStroke(h?: string) {
  if (h === 'critical') return '#ef4444'
  if (h === 'degraded') return '#f59e0b'
  return '#581c87'
}

function healthFill(h?: string) {
  if (h === 'critical') return '#ef4444'
  if (h === 'degraded') return '#f59e0b'
  if (h === 'healthy') return '#34d399'
  return '#64748b'
}

export default function EnvironmentOverview({ k8sGraph, traceGraph, clusters, incidents, environment }: EnvironmentOverviewProps) {
  const [nsFilter, setNsFilter] = useState('')
  const hasRuntime = (traceGraph?.nodes?.length || 0) > 0
  const hasK8s = (k8sGraph?.nodes?.length || 0) > 0
  const [source, setSource] = useState<'runtime' | 'k8s'>(() => (hasRuntime ? 'runtime' : 'k8s'))

  const useRuntime = source === 'runtime' && (traceGraph?.nodes?.length || 0) > 0
  const rawGraph = useRuntime ? traceGraph : k8sGraph
  const nodes = (rawGraph?.nodes || []).filter(n => !nsFilter || n.namespace === nsFilter || n.type === 'middleware')
  const edges = rawGraph?.edges || []

  const positioned = useMemo(() => layoutNodes(nodes, edges), [nodes, edges])
  const nodeMap = useMemo(() => {
    const m = new Map<string, TopoNode>()
    for (const n of positioned) {
      m.set(n.id, n)
      m.set(n.name, n)
    }
    return m
  }, [positioned])

  const { maxX, maxY } = graphBounds(positioned)
  const namespaces = [...new Set((k8sGraph?.nodes || []).map(n => n.namespace).filter(Boolean))].sort()
  const svcCount = nodes.filter(n => n.type === 'service').length
  const mwCount = nodes.filter(n => n.type === 'middleware').length
  const healthyCount = nodes.filter(n => n.health === 'healthy').length
  const healthRate = nodes.length ? Math.round((healthyCount / nodes.length) * 100) : 0

  return (
    <div className="glass rounded-xl border border-shark-border overflow-hidden">
      <div className="px-5 py-3 border-b border-shark-border flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <GitFork size={16} className="text-purple-400" /> 环境架构
        </h3>
        <span className="text-[10px] text-shark-muted">{environment || '—'}</span>
        <div className="flex rounded-lg border border-shark-border overflow-hidden text-[10px]">
          <button onClick={() => setSource('runtime')} disabled={!hasRuntime}
            className={cn('px-2.5 py-1 transition-colors', source === 'runtime' ? 'bg-purple-500/20 text-purple-200' : 'text-shark-muted hover:text-white', !hasRuntime && 'opacity-40')}>
            运行时 Trace
          </button>
          <button onClick={() => setSource('k8s')} disabled={!hasK8s}
            className={cn('px-2.5 py-1 transition-colors', source === 'k8s' ? 'bg-cyan-500/20 text-cyan-200' : 'text-shark-muted hover:text-white', !hasK8s && 'opacity-40')}>
            K8s 发现
          </button>
        </div>
        {namespaces.length > 0 && (
          <select value={nsFilter} onChange={e => setNsFilter(e.target.value)}
            className="bg-slate-950/70 border border-shark-border rounded px-2 py-1 text-[10px] text-white">
            <option value="">全部 Namespace</option>
            {namespaces.map(ns => <option key={ns} value={ns}>{ns}</option>)}
          </select>
        )}
        <span className="text-[10px] text-shark-muted ml-auto">
          {svcCount} 服务 · {mwCount} 中间件 · {edges.length} 连接 · 健康 {healthRate}%
        </span>
        <Link href="/topology" className="text-[10px] text-purple-300 hover:text-purple-200">Trace 详情 →</Link>
      </div>

      {/* Cluster strip */}
      {clusters.length > 0 && (
        <div className="px-5 py-2 border-b border-shark-border/50 flex gap-2 overflow-x-auto">
          {clusters.map(c => (
            <div key={c.id} className="shrink-0 flex items-center gap-2 px-2.5 py-1 rounded-md bg-slate-900/50 border border-shark-border text-[10px]">
              <span className={cn('w-1.5 h-1.5 rounded-full', healthDot[c.health])} />
              <span className="text-white font-medium">{c.name}</span>
              <span className="text-shark-muted">{c.provider} · {c.nodeCount} nodes</span>
            </div>
          ))}
        </div>
      )}

      <div className="p-4 overflow-auto min-h-[360px]">
        {positioned.length === 0 ? (
          <div className="h-[320px] flex flex-col items-center justify-center text-shark-muted gap-2">
            <Server size={32} className="opacity-30" />
            <p className="text-sm">暂无环境拓扑数据</p>
            <p className="text-xs">配置 K8s 发现或 ES trace_log 后自动展示</p>
          </div>
        ) : (
          <svg viewBox={`0 0 ${maxX} ${maxY}`} className="w-full min-w-[640px]" style={{ minHeight: 320 }}>
            {edges.map((e, i) => {
              const fromKey = e.from || e.source || ''
              const toKey = e.to || e.target || ''
              const from = nodeMap.get(fromKey)
              const to = nodeMap.get(toKey)
              if (!from || !to) return null
              const x1 = (from.x || 0) + 80, y1 = (from.y || 0) + 44
              const x2 = (to.x || 0) + 80, y2 = (to.y || 0) + 44
              const col = to.type === 'middleware' ? '#06b6d4' : '#a855f7'
              return (
                <g key={`${fromKey}-${toKey}-${i}`}>
                  <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={col} strokeWidth={1.5} opacity={0.55} markerEnd="url(#arrow-env)" />
                </g>
              )
            })}
            <defs>
              <marker id="arrow-env" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#a855f7" opacity={0.7} />
              </marker>
            </defs>
            {positioned.map(n => {
              const x = n.x || 0, y = n.y || 0
              const isMid = n.type === 'middleware'
              const w = 150, h = 72
              return (
                <Link key={n.id} href={isMid ? '/topology' : `/topology?service=${encodeURIComponent(n.name)}`}>
                  <g transform={`translate(${x},${y})`} className="cursor-pointer">
                    <rect width={w} height={h} rx={isMid ? 14 : 8}
                      fill="#0f172a" stroke={healthStroke(n.health)} strokeWidth={1.2} />
                    <circle cx="12" cy="14" r="4" fill={healthFill(n.health)} />
                    <text x="22" y="16" className="fill-shark-muted" style={{ fontSize: 8 }}>{isMid ? 'middleware' : (n.namespace || 'service')}</text>
                    <text x={w / 2} y="36" textAnchor="middle" fill="white" style={{ fontSize: 10, fontWeight: 600 }}>
                      {n.name.length > 18 ? n.name.slice(0, 16) + '…' : n.name}
                    </text>
                    <text x={w / 2} y="54" textAnchor="middle" fill="#94a3b8" style={{ fontSize: 8 }}>
                      {n.type === 'service'
                        ? `${n.readyReplicas ?? '?'}/${n.replicas ?? '?'} ready · ${n.version || '—'}`
                        : (n.host ? `${n.host}${n.port ? `:${n.port}` : ''}` : n.component || n.type)}
                    </text>
                    {(n.traceCount || 0) > 0 && (
                      <text x={w / 2} y="66" textAnchor="middle" fill="#c084fc" style={{ fontSize: 7 }}>
                        {n.traceCount} traces{n.errorCount ? ` · ${n.errorCount} err` : ''}
                      </text>
                    )}
                  </g>
                </Link>
              )
            })}
          </svg>
        )}
      </div>

      {/* Service inventory compact list when many nodes without edges */}
      {positioned.length > 0 && edges.length === 0 && (
        <div className="px-5 pb-4">
          <p className="text-[10px] text-amber-400 mb-2">未发现服务间连接，显示节点清单（K8s 发现依赖边可能尚未同步）</p>
        </div>
      )}
    </div>
  )
}

export function IncidentsSidebar({ incidents }: { incidents: Incident[] }) {
  return (
    <div className="w-[280px] shrink-0 border-l border-shark-border overflow-auto p-4">
      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
        <AlertTriangle size={16} className="text-red-400" /> 活跃事件
      </h3>
      {incidents.filter(i => i.status !== 'resolved').length === 0 && (
        <p className="text-xs text-shark-muted">无活跃告警</p>
      )}
      <div className="space-y-2">
        {incidents.filter(i => i.status !== 'resolved').slice(0, 8).map(inc => (
          <Link key={inc.id} href="/incidents"
            className={cn('block rounded-lg p-3 border transition-colors hover:border-shark-accent/30',
              inc.severity === 'critical' ? 'border-red-400/20 bg-red-400/5' : 'border-shark-border bg-shark-card/30')}>
            <div className="flex items-center gap-1 mb-1">
              <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium border', severityBadge[inc.severity])}>
                {inc.severity === 'critical' ? '紧急' : '警告'}
              </span>
              <span className="text-[10px] text-shark-muted">{fmtTime(inc.createdAt)}</span>
            </div>
            <p className="text-xs font-medium text-white line-clamp-2">{inc.title}</p>
          </Link>
        ))}
      </div>
      <Link href="/security" className="mt-4 flex items-center gap-2 text-xs text-shark-muted hover:text-white">
        <Shield size={14} /> 安全合规
      </Link>
    </div>
  )
}
