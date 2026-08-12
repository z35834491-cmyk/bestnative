'use client'

import { useCallback, useEffect, useState } from 'react'
import { BarChart3, Loader2, WifiOff, TrendingUp, Activity, Zap, Clock } from 'lucide-react'
import { cn } from '@/lib/utils'

const API = ''

interface ClusterInfo { id: string; name: string; provider: string; health: string; nodeCount: number }

export default function MonitoringPage() {
  const [clusters, setClusters] = useState<ClusterInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAll = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const cRes = await fetch(`${API}/api/topology/clusters`)
      const c = await cRes.json()
      setClusters(Array.isArray(c) ? c : [])
    } catch (e) { setError(e instanceof Error ? e.message : '无法连接 API') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  if (error && clusters.length === 0) {
    return <div className="h-full flex items-center justify-center"><div className="text-center space-y-3"><WifiOff size={40} className="text-red-400 mx-auto" /><p className="text-sm text-shark-muted">{error}</p><button onClick={fetchAll} className="text-xs text-shark-accent border border-shark-accent/30 px-3 py-1.5 rounded">重试</button></div></div>
  }

  if (loading) return <div className="h-full flex items-center justify-center"><Loader2 size={32} className="animate-spin text-shark-accent" /></div>

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2"><BarChart3 size={16} className="text-blue-400" /> 监控面板</h1>
        <button onClick={fetchAll} className="ml-auto text-xs text-shark-muted hover:text-white">刷新</button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="grid grid-cols-4 gap-4 mb-6">
          <MiniCard icon={Activity} label="集群数" value={clusters.length} color="text-blue-400" />
          <MiniCard icon={Zap} label="健康集群" value={clusters.filter(c => c.health === 'healthy').length} color="text-emerald-400" />
          <MiniCard icon={TrendingUp} label="总节点数" value={clusters.reduce((s, c) => s + c.nodeCount, 0)} color="text-purple-400" />
          <MiniCard icon={Clock} label="问题集群" value={clusters.filter(c => c.health !== 'healthy').length} color="text-amber-400" />
        </div>

        {/* Cluster health */}
        <div className="glass rounded-xl p-5 mb-6">
          <h3 className="text-sm font-semibold text-white mb-4">集群健康状态</h3>
          {clusters.length === 0 && <p className="text-xs text-shark-muted">未发现集群（配置 Kubeconfig 后自动发现）</p>}
          <div className="grid grid-cols-3 gap-4">
            {clusters.map(c => (
              <div key={c.id} className="p-4 rounded-lg border border-shark-border bg-shark-card/30">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-white">{c.name}</span>
                  <span className={cn('w-2 h-2 rounded-full', c.health === 'healthy' ? 'bg-emerald-400' : c.health === 'degraded' ? 'bg-amber-400' : 'bg-red-400')} />
                </div>
                <div className="text-xs text-shark-muted space-y-1">
                  <div>Provider: {c.provider}</div>
                  <div>Nodes: {c.nodeCount}</div>
                  <div className={cn('font-medium', c.health === 'healthy' ? 'text-emerald-400' : 'text-amber-400')}>{c.health === 'healthy' ? '● 正常' : '● 异常'}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Prometheus integration notice */}
        <div className="glass rounded-xl p-5 border border-shark-accent/10">
          <h3 className="text-sm font-semibold text-white mb-2">接入 Prometheus 后可查看</h3>
          <p className="text-xs text-shark-muted leading-relaxed">
            当前显示集群基本信息。配置 <code className="text-shark-accent bg-shark-accent/5 px-1 rounded">PROMETHEUS_URL</code> 环境变量后，可展示：CPU/内存/磁盘趋势图、Pod 健康状态、QPS/延迟/错误率时序、服务依赖调用链。
            参考 <code className="text-shark-accent bg-shark-accent/5 px-1 rounded">docs/INTEGRATION.md</code> 第 4 节。
          </p>
        </div>
      </div>
    </div>
  )
}

function MiniCard({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: number; color: string }) {
  return (
    <div className="glass rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-shark-muted">{label}</span>
        <Icon size={16} className={color} />
      </div>
      <span className="text-2xl font-bold text-white">{value}</span>
    </div>
  )
}
