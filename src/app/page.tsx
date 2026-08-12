'use client'

import { Fragment, useCallback, useEffect, useState } from 'react'
import { Activity, Server, AlertTriangle, TrendingUp, ArrowUp, ArrowDown, Loader2, WifiOff, RotateCw, X, Terminal, ChevronDown, ChevronRight, Boxes, Zap } from 'lucide-react'
import { cn, healthDot, fmtTime } from '@/lib/utils'
import type { ClusterInfo, Incident, TopoNode, TopologyGraph } from '@/lib/types'
import { severityBadge } from '@/lib/utils'

const API = ''

interface PodInfo {
  name: string; namespace: string; status: string; node: string
  restarts: number; ip: string; created_at: string
  containers: { name: string; image: string; ready: boolean }[]
  metrics?: { containers: { name: string; cpu_m: number; mem_mb: number }[] }
}

export default function DashboardPage() {
  const [topology, setTopology] = useState<TopologyGraph | null>(null)
  const [clusters, setClusters] = useState<ClusterInfo[]>([])
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nsFilter, setNsFilter] = useState('')

  const [expandedMap, setExpandedMap] = useState<Record<string, PodInfo[]>>({})
  const [podsLoading, setPodsLoading] = useState<Record<string, boolean>>({})
  const [podCounts, setPodCounts] = useState<Record<string, number>>({})

  const [logModal, setLogModal] = useState<{ pod: string; ns: string; container: string } | null>(null)
  const [logs, setLogs] = useState('')
  const [logsLoading, setLogsLoading] = useState(false)
  const [restarting, setRestarting] = useState<string | null>(null)
  const [actionNotice, setActionNotice] = useState<{ type: 'ok' | 'error'; text: string } | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [tRes, cRes, iRes] = await Promise.all([
        fetch(API + '/api/topology/graph'),
        fetch(API + '/api/topology/clusters'),
        fetch(API + '/api/incidents?limit=10'),
      ])
      const t = await tRes.json(); const c = await cRes.json(); const i = await iRes.json()
      setTopology(t); setClusters(Array.isArray(c) ? c : []); setIncidents(Array.isArray(i) ? i : [])
    } catch (e) { setError(e instanceof Error ? e.message : '无法连接 API') } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const toggleExpand = async (svc: TopoNode) => {
    if (expandedMap[svc.id]) {
      setExpandedMap(prev => { const n = { ...prev }; delete n[svc.id]; return n })
      return
    }
    setPodsLoading(prev => ({ ...prev, [svc.id]: true }))
    const ns = svc.namespace || 'default'
    try {
      const r = await fetch(API + '/api/topology/services/' + encodeURIComponent(svc.name) + '/pods?namespace=' + ns)
      const d = await r.json()
      setExpandedMap(prev => ({ ...prev, [svc.id]: d.pods || [] }))
      setPodCounts(prev => ({ ...prev, [svc.id]: (d.pods || []).length }))
    } catch {} finally {
      setPodsLoading(prev => ({ ...prev, [svc.id]: false }))
    }
  }

  const openLogs = async (podName: string, ns: string, container = '') => {
    setLogModal({ pod: podName, ns, container }); setLogsLoading(true)
    try {
      const contParam = container ? '&container=' + encodeURIComponent(container) : ''
      const r = await fetch(API + '/api/topology/pods/' + encodeURIComponent(podName) + '/logs?namespace=' + encodeURIComponent(ns) + '&tail=300' + contParam)
      const d = await r.json()
      setLogs(r.ok ? (d.logs || '(无日志)') : (d.detail || d.error || '日志获取失败'))
    } catch (e) { setLogs(e instanceof Error ? e.message : '日志获取失败') } finally { setLogsLoading(false) }
  }

  const doRestart = async (podName: string, ns: string, svcId: string) => {
    setRestarting(podName); setActionNotice(null)
    try {
      const resp = await fetch(API + '/api/topology/pods/' + encodeURIComponent(podName) + '/restart?namespace=' + encodeURIComponent(ns), { method: 'POST' })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok || data.restarted !== true) throw new Error(data.detail || data.error || '重启失败')
      setActionNotice({ type: 'ok', text: `已提交重启：${podName}` })
      setTimeout(async () => {
        const svc = (topology?.nodes || []).find(n => n.id === svcId)
        if (svc) {
          const r = await fetch(API + '/api/topology/services/' + encodeURIComponent(svc.name) + '/pods?namespace=' + ns)
          const d = await r.json()
          setExpandedMap(prev => ({ ...prev, [svcId]: d.pods || [] }))
          setPodCounts(prev => ({ ...prev, [svcId]: (d.pods || []).length }))
        }
      }, 3000)
    } catch (e) {
      setActionNotice({ type: 'error', text: e instanceof Error ? e.message : '重启失败' })
    } finally { setRestarting(null) }
  }

  const namespaces = [...new Set((topology?.nodes || []).map(n => n.namespace).filter(Boolean))].sort()
  const filteredNodes = nsFilter ? (topology?.nodes || []).filter(n => n.namespace === nsFilter) : (topology?.nodes || [])
  const svcNodes = filteredNodes.filter(n => n.type === 'service')
  const kpi = {
    totalServices: svcNodes.length,
    healthyRate: svcNodes.length ? Math.round((svcNodes.filter(n => n.health === 'healthy').length / svcNodes.length) * 100) : 0,
    activeIncidents: incidents.filter(i => i.status !== 'resolved').length,
    todayAlerts: incidents.length,
  }

  if (error) return <div className="h-full flex items-center justify-center"><div className="text-center space-y-3"><WifiOff size={40} className="text-red-400 mx-auto" /><p className="text-sm text-shark-muted">{error}</p><button onClick={fetchData} className="text-xs text-shark-accent border border-shark-accent/30 px-3 py-1.5 rounded">重试</button></div></div>
  if (loading) return <div className="h-full flex items-center justify-center"><Loader2 size={32} className="animate-spin text-shark-accent" /></div>

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14 gap-3">
        <span className="text-xs font-medium text-white">BestNative</span>
        <span className="text-[10px] text-shark-muted bg-shark-accent/10 border border-shark-accent/20 px-2 py-0.5 rounded">{process.env.NEXT_PUBLIC_ENV || 'unknown'}</span>
        <select value={nsFilter} onChange={e => setNsFilter(e.target.value)} className="ml-4 bg-shark-bg border border-shark-border rounded px-3 py-1 text-xs text-white focus:border-shark-accent outline-none">
          <option value="">全部 Namespace</option>
          {namespaces.map(ns => <option key={ns} value={ns}>{ns}</option>)}
        </select>
        <div className="ml-auto flex items-center gap-4 text-xs text-shark-muted">
          <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> 实时</span>
          <button onClick={fetchData} className="hover:text-white">刷新</button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 overflow-auto">
          <div className="p-6">
            {actionNotice && (
              <div className={cn('mb-4 px-4 py-2 rounded-lg border text-xs', actionNotice.type === 'ok' ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' : 'border-red-400/30 bg-red-400/10 text-red-300')}>
                {actionNotice.text}
              </div>
            )}
            <div className="grid grid-cols-5 gap-4 mb-6">
              <KpiCard icon={Server} label="服务数" value={kpi.totalServices} subtitle={`${nsFilter || '全部'} ns`} />
              <KpiCard icon={Activity} label="健康率" value={`${kpi.healthyRate}%`} subtitle={kpi.healthyRate > 90 ? '↑' : '↓'} trend="down" />
              <KpiCard icon={AlertTriangle} label="活跃告警" value={kpi.activeIncidents} subtitle="个" accent />
              <KpiCard icon={TrendingUp} label="今日告警" value={kpi.todayAlerts} subtitle="条" />
              <KpiCard icon={Server} label="集群" value={clusters.length} subtitle="个" />
            </div>

            <div className="glass rounded-xl overflow-hidden mb-4">
              <div className="px-5 py-3 border-b border-shark-border flex items-center">
                <h3 className="text-sm font-semibold text-white">服务列表 ({svcNodes.length})</h3>
              </div>
              {svcNodes.length === 0 ? (
                <p className="text-xs text-shark-muted px-5 py-8 text-center">暂无服务数据</p>
              ) : (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-shark-muted border-b border-shark-border bg-shark-card/30">
                      <th className="text-left py-3 px-5 w-8"></th>
                      <th className="text-left py-3 pr-3">服务名</th>
                      <th className="text-left py-3 pr-3">Namespace</th>
                      <th className="text-left py-3 pr-3">健康</th>
                      <th className="text-left py-3 pr-3">Pod</th>
                      <th className="text-left py-3 pr-3">版本</th>
                    </tr>
                  </thead>
                  <tbody>
                    {svcNodes.map(svc => {
                      const isOpen = !!expandedMap[svc.id]
                      const pods = expandedMap[svc.id] || []
                      const pCount = podCounts[svc.id]
                      return (
                        <Fragment key={svc.id}>
                          <tr key={svc.id} onClick={() => svc.type === 'service' && toggleExpand(svc)}
                            className={cn('border-b border-shark-border/50 transition-colors cursor-pointer hover:bg-white/[0.02]', isOpen && 'bg-shark-accent/5')}>
                            <td className="py-3 px-5">
                              {isOpen ? <ChevronDown size={14} className="text-shark-accent" /> : <ChevronRight size={14} className="text-shark-muted" />}
                            </td>
                            <td className="py-3 pr-3"><span className="text-white font-medium">{svc.name}</span></td>
                            <td className="py-3 pr-3 text-shark-muted">{svc.namespace}</td>
                            <td className="py-3 pr-3">
                              <span className={cn('px-1.5 py-0.5 rounded text-[10px]', svc.health === 'healthy' ? 'text-emerald-400 bg-emerald-400/10' : svc.health === 'degraded' ? 'text-amber-400 bg-amber-400/10' : 'text-red-400 bg-red-400/10')}>
                                {svc.health === 'healthy' ? '正常' : svc.health === 'degraded' ? '降级' : '严重'}
                              </span>
                            </td>
                            <td className="py-3 pr-3">
                              {podsLoading[svc.id] ? (
                                <Loader2 size={12} className="animate-spin text-shark-muted" />
                              ) : pCount !== undefined ? (
                                <span className={cn('flex items-center gap-1 px-2 py-0.5 rounded text-[10px]', pCount > 0 ? 'text-shark-accent bg-shark-accent/10' : 'text-shark-muted bg-shark-card')}>
                                  <Boxes size={12} /> {pCount} 个
                                </span>
                              ) : (
                                <span className="text-[10px] text-shark-muted">点击查看</span>
                              )}
                            </td>
                            <td className="py-3 pr-3 text-shark-muted">{svc.version || '—'}</td>
                          </tr>
                          {isOpen && (
                            <tr key={`pods-${svc.id}`} className="bg-shark-accent/[0.03] border-b border-shark-border/50">
                              <td colSpan={6} className="p-0">
                                <div className="ml-12 mr-5 my-2 px-4 py-3 rounded-lg border border-shark-accent/10 bg-black/10">
                                  {podsLoading[svc.id] ? (
                                    <div className="flex items-center gap-2 text-xs text-shark-muted py-2"><Loader2 size={14} className="animate-spin" /> 加载 Pod...</div>
                                  ) : pods.length === 0 ? (
                                    <p className="text-xs text-shark-muted py-2">未找到 Pod</p>
                                  ) : (
                                    <div className="space-y-1.5">
                                      {pods.map(p => {
                                        const m = p.metrics?.containers?.reduce((a, c) => ({ cpu: a.cpu + c.cpu_m, mem: a.mem + c.mem_mb }), { cpu: 0, mem: 0 }) || { cpu: 0, mem: 0 }
                                        const container = p.containers?.[0]?.name || ''
                                        return (
                                          <div key={p.name} className="flex items-center gap-3 py-1.5 px-3 rounded bg-shark-card/30 border border-shark-border/50 text-xs">
                                            <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', p.status === 'Running' ? 'bg-emerald-400' : 'bg-amber-400')} />
                                            <span className="text-white font-mono text-[11px] flex-1 truncate">{p.name}</span>
                                            <span className="text-shark-muted shrink-0">CPU {m.cpu.toFixed(0)}m</span>
                                            <span className="text-shark-muted shrink-0">内存 {m.mem.toFixed(0)}MB</span>
                                            <span className={cn('shrink-0', p.restarts > 5 ? 'text-red-400' : 'text-shark-muted')}>R:{p.restarts}</span>
                                            <button onClick={e => { e.stopPropagation(); openLogs(p.name, p.namespace, container) }}
                                              className="shrink-0 px-2 py-1 rounded text-[10px] text-shark-muted hover:text-shark-accent hover:bg-shark-accent/10 border border-transparent hover:border-shark-accent/20 transition-colors">
                                              <Terminal size={12} className="inline mr-1" />日志
                                            </button>
                                            <button onClick={e => { e.stopPropagation(); doRestart(p.name, p.namespace, svc.id) }}
                                              disabled={restarting === p.name}
                                              className="shrink-0 px-2 py-1 rounded text-[10px] text-shark-muted hover:text-red-400 hover:bg-red-400/10 border border-transparent hover:border-red-400/20 transition-colors disabled:opacity-50">
                                              <RotateCw size={12} className={cn('inline mr-1', restarting === p.name && 'animate-spin')} />重启
                                            </button>
                                          </div>
                                        )
                                      })}
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>

            <div className="glass rounded-xl p-4">
              <h3 className="text-sm font-semibold text-white mb-2">集群概览</h3>
              <div className="flex gap-3 overflow-x-auto">
                {clusters.length === 0 && <p className="text-xs text-shark-muted">未发现集群</p>}
                {clusters.map(c => (
                  <div key={c.id} className="min-w-[160px] p-3 rounded-lg border border-shark-border bg-shark-card/30">
                    <div className="flex items-center justify-between mb-1"><span className="text-xs font-medium text-white">{c.name}</span><span className={cn('w-2 h-2 rounded-full shrink-0', healthDot[c.health])} /></div>
                    <div className="text-[10px] text-shark-muted">{c.nodeCount} Nodes · {c.provider}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="w-[300px] border-l border-shark-border overflow-auto p-4">
          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2"><AlertTriangle size={16} className="text-red-400" /> 实时告警</h3>
          {incidents.length === 0 && <p className="text-xs text-shark-muted">无活跃告警</p>}
          <div className="space-y-3">
            {incidents.map(inc => (
              <div key={inc.id} className={cn('rounded-lg p-3 border', inc.severity === 'critical' ? 'border-red-400/20 bg-red-400/5' : 'border-shark-border bg-shark-card/30')}>
                <div className="flex items-center gap-1 mb-1">
                  <span className={cn('px-1.5 py-0.5 rounded text-[10px] font-medium border', severityBadge[inc.severity])}>{inc.severity === 'critical' ? '紧急' : inc.severity === 'warning' ? '警告' : '信息'}</span>
                  <span className="text-[10px] text-shark-muted">{fmtTime(inc.createdAt)}</span>
                </div>
                <p className="text-xs font-medium text-white mb-1">{inc.title}</p>
                <p className="text-[10px] text-shark-muted line-clamp-1">{inc.affectedServices?.join(', ') || inc.source}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {logModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center" onClick={() => setLogModal(null)}>
          <div className="bg-shark-bg border border-shark-border rounded-xl w-[800px] max-h-[80vh] flex flex-col shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center px-4 py-3 border-b border-shark-border">
              <Terminal size={14} className="text-shark-accent mr-2" />
              <span className="text-sm font-medium text-white">{logModal.pod}</span>
              <span className="ml-2 text-xs text-shark-muted">{logModal.ns}{logModal.container ? ' · ' + logModal.container : ''}</span>
              <button onClick={() => setLogModal(null)} className="ml-auto text-shark-muted hover:text-white"><X size={16} /></button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {logsLoading ? <div className="flex items-center justify-center py-8"><Loader2 size={20} className="animate-spin text-shark-accent" /></div> :
                <pre className="text-xs text-slate-300 font-mono whitespace-pre overflow-x-auto leading-6 tabular-nums">{logs}</pre>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function KpiCard({ icon: Icon, label, value, subtitle, trend, accent }: { icon: React.ElementType; label: string; value: string | number; subtitle: string; trend?: 'up' | 'down'; accent?: boolean }) {
  return (
    <div className={cn('glass rounded-xl p-4', accent && 'border-l-2 border-l-red-400')}>
      <div className="flex items-center justify-between mb-2"><span className="text-xs text-shark-muted">{label}</span><Icon size={16} className={accent ? 'text-red-400' : 'text-shark-muted'} /></div>
      <div className="flex items-baseline gap-1"><span className="text-2xl font-bold text-white">{value}</span><span className="text-xs text-shark-muted">{subtitle}</span></div>
      {trend && <div className={cn('flex items-center gap-1 mt-1 text-xs', trend === 'up' ? 'text-emerald-400' : 'text-amber-400')}>{trend === 'up' ? <ArrowUp size={12} /> : <ArrowDown size={12} />} 较昨日</div>}
    </div>
  )
}
