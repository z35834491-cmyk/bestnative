'use client'

import { useCallback, useEffect, useState } from 'react'
import { ClipboardCheck, Loader2, WifiOff, Shield, Bug, CheckCircle2, Clock } from 'lucide-react'
import { cn, fmtTime } from '@/lib/utils'

const API = ''

export default function InspectionsPage() {
  const [stats, setStats] = useState<Record<string, unknown>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAll = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [sRes] = await Promise.all([fetch(`${API}/api/security/stats`)])
      setStats(await sRes.json())
    } catch (e) { setError(e instanceof Error ? e.message : '无法连接 API') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchAll() }, [fetchAll])

  if (error) {
    return <div className="h-full flex items-center justify-center"><div className="text-center space-y-3"><WifiOff size={40} className="text-red-400 mx-auto" /><p className="text-sm text-shark-muted">{error}</p><button onClick={fetchAll} className="text-xs text-shark-accent border border-shark-accent/30 px-3 py-1.5 rounded">重试</button></div></div>
  }

  if (loading) return <div className="h-full flex items-center justify-center"><Loader2 size={32} className="animate-spin text-shark-accent" /></div>

  const inspections = [
    { name: '安全漏洞巡检', schedule: '每日 03:00', status: 'active', icon: Shield, description: '全平台自动扫描：子域名枚举 → 端口探测 → CVE 扫描 → AI 分析报告', source: 'Security Agent' },
    { name: 'K8s 服务发现', schedule: '每 5 分钟', status: 'active', icon: CheckCircle2, description: '自动发现 Namespace / Deployment / Service / Pod，识别 K8s↔VM 桥接依赖', source: 'Discovery Engine' },
    { name: '集群健康检查', schedule: '每 5 分钟', status: 'active', icon: Clock, description: '检查所有集群和节点健康状态，异常自动建 Incident', source: 'Monitor Agent' },
    { name: '日志异常检测', schedule: '持续', status: 'configuring', icon: Bug, description: 'ClickHouse 日志模式匹配，异常签名自动入库', source: 'Knowledge Agent' },
    { name: '成本异常检测', schedule: '每日 09:00', status: 'configuring', icon: Shield, description: 'AWS Cost Explorer 日度费用对比，异常突增告警', source: 'Cost Agent' },
  ]

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2"><ClipboardCheck size={16} className="text-emerald-400" /> 巡检任务</h1>
        <button onClick={fetchAll} className="ml-auto text-xs text-shark-muted hover:text-white">刷新</button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        {/* Summary bar */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <SummaryCard label="活跃巡检" value={inspections.filter(i => i.status === 'active').length} color="text-emerald-400" />
          <SummaryCard label="待配置" value={inspections.filter(i => i.status === 'configuring').length} color="text-amber-400" />
          <SummaryCard label="总扫描数" value={Number(stats?.totalScans) || 0} color="text-purple-400" />
        </div>

        <div className="glass rounded-xl p-5">
          <h3 className="text-sm font-semibold text-white mb-4">巡检任务列表</h3>
          <div className="space-y-3">
            {inspections.map((ins, i) => (
              <div key={i} className="p-4 rounded-lg border border-shark-border bg-shark-card/30">
                <div className="flex items-center gap-3 mb-2">
                  <ins.icon size={18} className={ins.status === 'active' ? 'text-emerald-400' : 'text-amber-400'} />
                  <span className="text-sm font-medium text-white">{ins.name}</span>
                  <span className={cn('text-[10px] px-2 py-0.5 rounded border ml-auto',
                    ins.status === 'active' ? 'text-emerald-400 border-emerald-400/20 bg-emerald-400/5' : 'text-amber-400 border-amber-400/20 bg-amber-400/5'
                  )}>{ins.status === 'active' ? '运行中' : '待配置'}</span>
                </div>
                <p className="text-xs text-shark-muted mb-2">{ins.description}</p>
                <div className="flex items-center gap-4 text-[10px] text-shark-muted">
                  <span className="flex items-center gap-1"><Clock size={10} /> {ins.schedule}</span>
                  <span>来源: {ins.source}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function SummaryCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="glass rounded-xl p-4">
      <span className="text-xs text-shark-muted">{label}</span>
      <p className={cn('text-2xl font-bold mt-1', color)}>{value}</p>
    </div>
  )
}
