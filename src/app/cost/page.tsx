'use client'

import { useCallback, useEffect, useState } from 'react'
import { DollarSign, Loader2, WifiOff, TrendingDown, TrendingUp, Server } from 'lucide-react'
import { cn } from '@/lib/utils'

const API = ''

interface ClusterInfo { id: string; name: string; provider: string; nodeCount: number; health: string }

export default function CostPage() {
  const [clusters, setClusters] = useState<ClusterInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const cRes = await fetch(`${API}/api/topology/clusters`)
      setClusters(await cRes.json())
    } catch (e) { setError(e instanceof Error ? e.message : '无法连接 API') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  if (error && clusters.length === 0) {
    return <div className="h-full flex items-center justify-center"><div className="text-center space-y-3"><WifiOff size={40} className="text-red-400 mx-auto" /><p className="text-sm text-shark-muted">{error}</p><button onClick={fetchData} className="text-xs text-shark-accent border border-shark-accent/30 px-3 py-1.5 rounded">重试</button></div></div>
  }

  if (loading) return <div className="h-full flex items-center justify-center"><Loader2 size={32} className="animate-spin text-shark-accent" /></div>

  const totalNodes = clusters.reduce((s, c) => s + c.nodeCount, 0)
  const ec2Estimate = totalNodes * 0.07 * 730 // rough: m5.large × hours
  const otherEstimate = totalNodes * 0.03 * 730

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2"><DollarSign size={16} className="text-amber-400" /> 成本分析</h1>
        <span className="ml-3 text-xs text-shark-muted">基于资源发现估算 · 接入 AWS Cost Explorer 后精确化</span>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="grid grid-cols-4 gap-4 mb-6">
          <CostCard label="本月估算" value={`$${ec2Estimate.toFixed(0)}`} sub="EC2 费用" trend="up" />
          <CostCard label="其他服务" value={`$${otherEstimate.toFixed(0)}`} sub="ELB / EBS / Data" />
          <CostCard label="总节点" value={String(totalNodes)} sub="跨所有集群" />
          <CostCard label="集群数" value={String(clusters.length)} sub={clusters.map(c => c.name).join(', ') || '—'} />
        </div>

        <div className="glass rounded-xl p-5 mb-6">
          <h3 className="text-sm font-semibold text-white mb-3">集群资源分布</h3>
          {clusters.length === 0 && <p className="text-xs text-shark-muted">未发现集群</p>}
          {clusters.map(c => (
            <div key={c.id} className="flex items-center justify-between py-3 border-b border-shark-border last:border-0">
              <div className="flex items-center gap-3">
                <Server size={16} className={cn(c.health === 'healthy' ? 'text-emerald-400' : 'text-amber-400')} />
                <div>
                  <p className="text-sm text-white font-medium">{c.name}</p>
                  <p className="text-xs text-shark-muted">{c.provider} · {c.health}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm text-white font-medium">{c.nodeCount} Nodes</p>
                <p className="text-xs text-shark-muted">≈ ${(c.nodeCount * 0.07 * 730).toFixed(0)}/mo</p>
              </div>
            </div>
          ))}
        </div>

        <div className="glass rounded-xl p-5 border border-shark-accent/10">
          <h3 className="text-sm font-semibold text-white mb-2">接入 AWS Cost Explorer</h3>
          <p className="text-xs text-shark-muted leading-relaxed">
            当前显示基于资源发现数量的粗略估算。配置 <code className="text-shark-accent bg-shark-accent/5 px-1 rounded">AWS</code> 只读角色后，可展示：真实月度/日度费用、按服务拆分、RI/Spot 节省建议、预算告警。
            参考 <code className="text-shark-accent bg-shark-accent/5 px-1 rounded">docs/INTEGRATION.md</code> 配置 AWS Provider。
          </p>
        </div>
      </div>
    </div>
  )
}

function CostCard({ label, value, sub, trend }: { label: string; value: string; sub: string; trend?: 'up' | 'down' }) {
  return (
    <div className="glass rounded-xl p-4">
      <span className="text-xs text-shark-muted">{label}</span>
      <div className="flex items-baseline gap-2 mt-1 mb-1">
        <span className="text-2xl font-bold text-white">{value}</span>
        {trend && (trend === 'up' ? <TrendingUp size={14} className="text-red-400" /> : <TrendingDown size={14} className="text-emerald-400" />)}
      </div>
      <span className="text-[10px] text-shark-muted">{sub}</span>
    </div>
  )
}
