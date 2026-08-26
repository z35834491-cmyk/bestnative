'use client'

import { Fragment, useCallback, useEffect, useState } from 'react'
import { Boxes, ChevronDown, ChevronRight, Loader2, RotateCw, Terminal, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { apiFetch, apiJson, readApiError } from '@/lib/api'
import { ErrorState, LoadingSpinner } from '@/components/ui/AsyncState'
import type { TopoNode, TopologyGraph } from '@/lib/types'

interface PodInfo {
  name: string
  namespace: string
  status: string
  node: string
  restarts: number
  ip: string
  created_at: string
  containers: { name: string; image: string; ready: boolean }[]
  metrics?: { containers: { name: string; cpu_m: number; mem_mb: number }[] }
}

export default function PodsPage() {
  const [topology, setTopology] = useState<TopologyGraph | null>(null)
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

  const fetchTopology = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const t = await apiJson<TopologyGraph>('/api/topology/graph')
      setTopology(t)
    } catch (e) {
      setError(e instanceof Error ? e.message : '无法连接 API')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchTopology() }, [fetchTopology])

  const toggleExpand = async (svc: TopoNode) => {
    if (expandedMap[svc.id]) {
      setExpandedMap(prev => { const n = { ...prev }; delete n[svc.id]; return n })
      return
    }
    setPodsLoading(prev => ({ ...prev, [svc.id]: true }))
    const ns = svc.namespace || 'default'
    try {
      const d = await apiJson<{ pods?: PodInfo[] }>(
        `/api/topology/services/${encodeURIComponent(svc.name)}/pods?namespace=${encodeURIComponent(ns)}`
      )
      setExpandedMap(prev => ({ ...prev, [svc.id]: d.pods || [] }))
      setPodCounts(prev => ({ ...prev, [svc.id]: (d.pods || []).length }))
    } catch {
      setActionNotice({ type: 'error', text: 'Pod 列表加载失败' })
    } finally {
      setPodsLoading(prev => ({ ...prev, [svc.id]: false }))
    }
  }

  const openLogs = async (podName: string, ns: string, container = '') => {
    setLogModal({ pod: podName, ns, container })
    setLogsLoading(true)
    try {
      const contParam = container ? `&container=${encodeURIComponent(container)}` : ''
      const res = await apiFetch(
        `/api/topology/pods/${encodeURIComponent(podName)}/logs?namespace=${encodeURIComponent(ns)}&tail=300${contParam}`
      )
      const d = await res.json()
      setLogs(res.ok ? (d.logs || '(无日志)') : await readApiError(res))
    } catch (e) {
      setLogs(e instanceof Error ? e.message : '日志获取失败')
    } finally {
      setLogsLoading(false)
    }
  }

  const doRestart = async (podName: string, ns: string, svcId: string) => {
    if (!confirm(`确认重启 Pod ${podName}？`)) return
    setRestarting(podName)
    setActionNotice(null)
    try {
      const resp = await apiFetch(
        `/api/topology/pods/${encodeURIComponent(podName)}/restart?namespace=${encodeURIComponent(ns)}`,
        { method: 'POST' }
      )
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok || data.restarted !== true) throw new Error(await readApiError(resp))
      setActionNotice({ type: 'ok', text: `已提交重启：${podName}` })
      setTimeout(async () => {
        const svc = (topology?.nodes || []).find(n => n.id === svcId)
        if (svc) {
          const d = await apiJson<{ pods?: PodInfo[] }>(
            `/api/topology/services/${encodeURIComponent(svc.name)}/pods?namespace=${encodeURIComponent(ns)}`
          )
          setExpandedMap(prev => ({ ...prev, [svcId]: d.pods || [] }))
          setPodCounts(prev => ({ ...prev, [svcId]: (d.pods || []).length }))
        }
      }, 3000)
    } catch (e) {
      setActionNotice({ type: 'error', text: e instanceof Error ? e.message : '重启失败' })
    } finally {
      setRestarting(null)
    }
  }

  const namespaces = [...new Set((topology?.nodes || []).map(n => n.namespace).filter(Boolean))].sort()
  const svcNodes = (nsFilter
    ? (topology?.nodes || []).filter(n => n.namespace === nsFilter)
    : (topology?.nodes || [])
  ).filter(n => n.type === 'service')

  const totalPods = Object.values(podCounts).reduce((a, b) => a + b, 0)

  if (loading) return <LoadingSpinner />
  if (error) return <ErrorState message={error} onRetry={fetchTopology} />

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14 gap-3">
        <Boxes size={16} className="text-shark-accent" />
        <h1 className="text-sm font-semibold text-white">Pod 管理</h1>
        <span className="text-xs text-shark-muted">{svcNodes.length} 服务 · {totalPods || '—'} Pod 已加载</span>
        <select value={nsFilter} onChange={e => setNsFilter(e.target.value)}
          className="ml-2 bg-shark-bg border border-shark-border rounded px-3 py-1 text-xs text-white outline-none">
          <option value="">全部 Namespace</option>
          {namespaces.map(ns => <option key={ns} value={ns}>{ns}</option>)}
        </select>
        <button onClick={fetchTopology} className="ml-auto text-xs text-shark-muted hover:text-white">刷新</button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        {actionNotice && (
          <div className={cn('mb-4 px-4 py-2 rounded-lg border text-xs',
            actionNotice.type === 'ok' ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' : 'border-red-400/30 bg-red-400/10 text-red-300')}>
            {actionNotice.text}
          </div>
        )}

        <div className="glass rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-shark-border">
            <h3 className="text-sm font-semibold text-white">服务 → Pod 列表</h3>
            <p className="text-[10px] text-shark-muted mt-0.5">点击服务行展开 Pod，支持查看日志和重启</p>
          </div>

          {svcNodes.length === 0 ? (
            <p className="text-xs text-shark-muted px-5 py-8 text-center">暂无服务数据，请先运行 K8s 发现</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-shark-muted border-b border-shark-border bg-shark-card/30">
                  <th className="text-left py-3 px-5 w-8" />
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
                      <tr onClick={() => toggleExpand(svc)}
                        className={cn('border-b border-shark-border/50 transition-colors cursor-pointer hover:bg-white/[0.02]', isOpen && 'bg-shark-accent/5')}>
                        <td className="py-3 px-5">
                          {isOpen ? <ChevronDown size={14} className="text-shark-accent" /> : <ChevronRight size={14} className="text-shark-muted" />}
                        </td>
                        <td className="py-3 pr-3"><span className="text-white font-medium">{svc.name}</span></td>
                        <td className="py-3 pr-3 text-shark-muted">{svc.namespace}</td>
                        <td className="py-3 pr-3">
                          <span className={cn('px-1.5 py-0.5 rounded text-[10px]',
                            svc.health === 'healthy' ? 'text-emerald-400 bg-emerald-400/10' :
                            svc.health === 'degraded' ? 'text-amber-400 bg-amber-400/10' : 'text-red-400 bg-red-400/10')}>
                            {svc.health === 'healthy' ? '正常' : svc.health === 'degraded' ? '降级' : '严重'}
                          </span>
                        </td>
                        <td className="py-3 pr-3">
                          {podsLoading[svc.id] ? (
                            <Loader2 size={12} className="animate-spin text-shark-muted" />
                          ) : pCount !== undefined ? (
                            <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] text-shark-accent bg-shark-accent/10">
                              <Boxes size={12} /> {pCount} 个
                            </span>
                          ) : (
                            <span className="text-[10px] text-shark-muted">点击展开</span>
                          )}
                        </td>
                        <td className="py-3 pr-3 text-shark-muted">{svc.version || '—'}</td>
                      </tr>
                      {isOpen && (
                        <tr className="bg-shark-accent/[0.03] border-b border-shark-border/50">
                          <td colSpan={6} className="p-0">
                            <div className="ml-12 mr-5 my-2 px-4 py-3 rounded-lg border border-shark-accent/10 bg-black/10">
                              {podsLoading[svc.id] ? (
                                <div className="flex items-center gap-2 text-xs text-shark-muted py-2">
                                  <Loader2 size={14} className="animate-spin" /> 加载 Pod...
                                </div>
                              ) : pods.length === 0 ? (
                                <p className="text-xs text-shark-muted py-2">未找到 Pod</p>
                              ) : (
                                <div className="space-y-1.5">
                                  {pods.map(p => {
                                    const m = p.metrics?.containers?.reduce(
                                      (a, c) => ({ cpu: a.cpu + c.cpu_m, mem: a.mem + c.mem_mb }),
                                      { cpu: 0, mem: 0 }
                                    ) || { cpu: 0, mem: 0 }
                                    const container = p.containers?.[0]?.name || ''
                                    return (
                                      <div key={p.name} className="flex items-center gap-3 py-1.5 px-3 rounded bg-shark-card/30 border border-shark-border/50 text-xs flex-wrap">
                                        <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', p.status === 'Running' ? 'bg-emerald-400' : 'bg-amber-400')} />
                                        <span className="text-white font-mono text-[11px] flex-1 min-w-[180px] truncate">{p.name}</span>
                                        <span className="text-shark-muted shrink-0">{p.node}</span>
                                        <span className="text-shark-muted shrink-0">CPU {m.cpu.toFixed(0)}m</span>
                                        <span className="text-shark-muted shrink-0">内存 {m.mem.toFixed(0)}MB</span>
                                        <span className={cn('shrink-0', p.restarts > 5 ? 'text-red-400' : 'text-shark-muted')}>R:{p.restarts}</span>
                                        <button onClick={e => { e.stopPropagation(); openLogs(p.name, p.namespace, container) }}
                                          className="shrink-0 px-2 py-1 rounded text-[10px] text-shark-muted hover:text-shark-accent hover:bg-shark-accent/10 border border-transparent hover:border-shark-accent/20">
                                          <Terminal size={12} className="inline mr-1" />日志
                                        </button>
                                        <button onClick={e => { e.stopPropagation(); doRestart(p.name, p.namespace, svc.id) }}
                                          disabled={restarting === p.name}
                                          className="shrink-0 px-2 py-1 rounded text-[10px] text-shark-muted hover:text-red-400 hover:bg-red-400/10 border border-transparent hover:border-red-400/20 disabled:opacity-50">
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
      </div>

      {logModal && (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center" onClick={() => setLogModal(null)}>
          <div className="bg-shark-bg border border-shark-border rounded-xl w-[800px] max-h-[80vh] flex flex-col shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center px-4 py-3 border-b border-shark-border">
              <Terminal size={14} className="text-shark-accent mr-2" />
              <span className="text-sm font-medium text-white">{logModal.pod}</span>
              <span className="ml-2 text-xs text-shark-muted">{logModal.ns}{logModal.container ? ` · ${logModal.container}` : ''}</span>
              <button onClick={() => setLogModal(null)} className="ml-auto text-shark-muted hover:text-white"><X size={16} /></button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {logsLoading ? <LoadingSpinner /> :
                <pre className="text-xs text-slate-300 font-mono whitespace-pre overflow-x-auto leading-6">{logs}</pre>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
