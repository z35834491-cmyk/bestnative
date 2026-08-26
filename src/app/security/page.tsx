'use client'

import { useCallback, useEffect, useState } from 'react'
import { Shield, Play, Clock, AlertTriangle, CheckCircle2, Loader2, WifiOff, Bug, Target } from 'lucide-react'
import { cn, fmtTime } from '@/lib/utils'

const API = ''

interface Vuln { id: string; title: string; severity: string; type: string; target: string; endpoint: string; foundBy: string; cve: string; cvssScore: number | null; description: string; recommendation: string; status: string; createdAt: string }
interface Scan { id: string; target: string; scope: string; status: string; assetCount: number; vulnCount: number; reportPreview?: string; startedAt: string | null; completedAt: string | null }
interface Stats { bySeverity: Record<string,number>; byStatus: Record<string,number>; totalScans: number }
interface ToolStatus { network: Record<string, boolean>; k8sConfigured: boolean; extraTargets: string[]; hints: string[] }

export default function SecurityPage() {
  const [tab, setTab] = useState<'overview'|'scan'|'vulns'>('overview')
  const [stats, setStats] = useState<Stats | null>(null)
  const [scans, setScans] = useState<Scan[]>([])
  const [vulns, setVulns] = useState<Vuln[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [scanTarget, setScanTarget] = useState('')
  const [scanning, setScanning] = useState(false)
  const [tools, setTools] = useState<ToolStatus | null>(null)
  const [filterSev, setFilterSev] = useState('')

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [sRes, scRes, vRes, tRes] = await Promise.all([
        fetch(`${API}/api/security/stats`),
        fetch(`${API}/api/security/scans?limit=30`),
        fetch(`${API}/api/security/vulnerabilities?limit=100${filterSev ? `&severity=${filterSev}` : ''}`),
        fetch(`${API}/api/security/tools`),
      ])
      setStats(await sRes.json())
      const sc = await scRes.json()
      setScans(Array.isArray(sc) ? sc : [])
      const v = await vRes.json()
      setVulns(Array.isArray(v) ? v : [])
      setTools(tRes.ok ? await tRes.json() : null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '无法连接 API')
    } finally { setLoading(false) }
  }, [filterSev])

  useEffect(() => { fetchAll() }, [fetchAll])

  const startScan = async () => {
    if (!scanTarget.trim()) return
    setScanning(true)
    try {
      await fetch(`${API}/api/security/scans`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: scanTarget, scope: 'manual' }),
      })
      setScanTarget('')
      setTimeout(fetchAll, 5000)
    } catch {} finally { setScanning(false) }
  }

  const startFullScan = async () => {
    setScanning(true)
    try {
      await fetch(`${API}/api/security/scans`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope: 'full_platform' }),
      })
      setTimeout(fetchAll, 8000)
    } catch {} finally { setScanning(false) }
  }

  if (error && !stats) {
    return <div className="h-full flex items-center justify-center"><div className="text-center space-y-3"><WifiOff size={40} className="text-red-400 mx-auto" /><p className="text-sm text-shark-muted">{error}</p><button onClick={fetchAll} className="text-xs text-shark-accent border border-shark-accent/30 px-3 py-1.5 rounded">重试</button></div></div>
  }

  if (loading) return <div className="h-full flex items-center justify-center"><Loader2 size={32} className="animate-spin text-shark-accent" /></div>

  const sevStyles: Record<string, string> = { critical: 'text-red-400 bg-red-400/10 border-red-400/20', high: 'text-orange-400 bg-orange-400/10 border-orange-400/20', medium: 'text-amber-400 bg-amber-400/10 border-amber-400/20', low: 'text-blue-400 bg-blue-400/10 border-blue-400/20', info: 'text-shark-muted bg-shark-card border-shark-border' }

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2"><Shield size={16} className="text-purple-400" /> 安全合规</h1>
        <span className="ml-2 text-[10px] text-shark-muted">漏洞扫描 · 渗透测试</span>
        <div className="ml-4 flex gap-1">
          {[{k:'overview',l:'概览'},{k:'scan',l:'漏洞扫描'},{k:'vulns',l:'漏洞清单'}].map(t => (
            <button key={t.k} onClick={() => setTab(t.k as typeof tab)} className={cn('px-3 py-1.5 text-xs rounded transition-colors', tab === t.k ? 'bg-shark-accent/20 text-shark-accent' : 'text-shark-muted hover:text-white')}>{t.l}</button>
          ))}
        </div>
        <button onClick={fetchAll} className="ml-auto text-xs text-shark-muted hover:text-white">刷新</button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        {tab === 'overview' && stats && (
          <div className="space-y-6">
            <div className="grid grid-cols-4 gap-4">
              <StatCard icon={Shield} label="总扫描次数" value={stats.totalScans} color="text-purple-400" />
              <StatCard icon={Bug} label="严重漏洞" value={stats.bySeverity?.critical || 0} color="text-red-400" />
              <StatCard icon={AlertTriangle} label="高危漏洞" value={stats.bySeverity?.high || 0} color="text-orange-400" />
              <StatCard icon={CheckCircle2} label="中低危" value={(stats.bySeverity?.medium || 0) + (stats.bySeverity?.low || 0)} color="text-amber-400" />
            </div>
            <div className="glass rounded-xl p-5">
              <h3 className="text-sm font-semibold text-white mb-3">最近扫描</h3>
              {scans.slice(0, 5).map(s => (
                <div key={s.id} className="py-2 border-b border-shark-border last:border-0 text-xs space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-white">{s.target}</span>
                    <span className={cn(s.status === 'completed' ? 'text-emerald-400' : s.status === 'failed' ? 'text-red-400' : 'text-amber-400')}>{s.status}</span>
                    <span className="text-shark-muted">{s.vulnCount} 漏洞 · {s.assetCount} 资产</span>
                  </div>
                  {s.reportPreview && <p className="text-shark-muted line-clamp-1">{s.reportPreview}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'scan' && (
          <div className="space-y-6">
            {tools && (
              <div className="glass rounded-xl p-5 space-y-3">
                <h3 className="text-sm font-semibold text-white">扫描能力</h3>
                <p className="text-xs text-shark-muted">subfinder 子域名 → httpx 存活 → nmap 端口/服务 → nuclei CVE/Web 漏洞</p>
                <div className="flex flex-wrap gap-2 text-xs">
                  {Object.entries(tools.network).map(([k, ok]) => (
                    <span key={k} className={cn('px-2 py-1 rounded border', ok ? 'text-emerald-400 border-emerald-400/30' : 'text-red-400 border-red-400/30')}>{k} {ok ? '✓' : '✗'}</span>
                  ))}
                  <span className={cn('px-2 py-1 rounded border', tools.k8sConfigured ? 'text-emerald-400 border-emerald-400/30' : 'text-amber-400 border-amber-400/30')}>k8s {tools.k8sConfigured ? '✓' : '—'}</span>
                </div>
                {(tools.hints || []).map((h, i) => <p key={i} className="text-xs text-amber-400/90">· {h}</p>)}
              </div>
            )}
            <div className="glass rounded-xl p-5 space-y-4">
              <h3 className="text-sm font-semibold text-white">手动渗透 / 漏洞扫描</h3>
              <div className="flex gap-3">
                <input value={scanTarget} onChange={e => setScanTarget(e.target.value)} placeholder="对外域名、Ingress 或 IP，如 api.example.com" className="flex-1 bg-shark-bg border border-shark-border rounded-lg px-4 py-2 text-sm text-white placeholder-shark-muted/50 outline-none focus:border-shark-accent" onKeyDown={e => e.key === 'Enter' && startScan()} />
                <button onClick={startScan} disabled={scanning || !scanTarget.trim()} className="flex items-center gap-2 px-4 py-2 bg-shark-accent/20 border border-shark-accent/30 text-shark-accent text-sm rounded-lg hover:bg-shark-accent/30 disabled:opacity-50">
                  <Play size={14} /> {scanning ? '扫描中...' : '开始扫描'}
                </button>
                <button onClick={startFullScan} disabled={scanning} className="flex items-center gap-2 px-4 py-2 border border-shark-border text-shark-muted text-sm rounded-lg hover:text-white disabled:opacity-50">
                  <Target size={14} /> 全平台巡检
                </button>
              </div>
            </div>
            <div className="glass rounded-xl p-5">
              <h3 className="text-sm font-semibold text-white mb-3">扫描历史</h3>
              {scans.length === 0 && <p className="text-xs text-shark-muted">暂无记录</p>}
              {scans.map(s => (
                <div key={s.id} className="p-3 mb-2 rounded-lg border border-shark-border text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-white font-medium">{s.target}</span>
                    <span className="text-shark-muted">{s.scope === 'full_platform' ? '全平台' : '手动'}</span>
                    <span className={cn(s.status === 'completed' ? 'text-emerald-400' : s.status === 'failed' ? 'text-red-400' : 'text-amber-400')}>{s.status}</span>
                    <span className="text-shark-muted">{s.vulnCount} 漏洞 · {s.assetCount} 资产</span>
                    <span className="text-shark-muted"><Clock size={12} className="inline mr-1" />{fmtTime(s.completedAt || s.startedAt || '')}</span>
                  </div>
                  {s.reportPreview && <p className="text-shark-muted whitespace-pre-wrap">{s.reportPreview}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === 'vulns' && (
          <div>
            <div className="flex gap-2 mb-4">
              {['','critical','high','medium','low'].map(sev => (
                <button key={sev} onClick={() => setFilterSev(sev)} className={cn('px-3 py-1.5 text-xs rounded border transition-colors', filterSev === sev ? 'border-shark-accent bg-shark-accent/10 text-shark-accent' : 'border-shark-border text-shark-muted hover:text-white')}>{sev || '全部'}</button>
              ))}
            </div>
            {vulns.length === 0 && <p className="text-xs text-shark-muted">无漏洞记录 — 先在「漏洞扫描」对对外域名执行扫描</p>}
            <div className="space-y-3">
              {vulns.map(v => (
                <div key={v.id} className="p-4 rounded-xl glass border border-shark-border">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={cn('px-2 py-0.5 rounded text-[10px] font-medium border', sevStyles[v.severity] || sevStyles.medium)}>{v.severity.toUpperCase()}</span>
                    <span className="text-sm font-medium text-white">{v.title}</span>
                    {v.cve && <span className="text-[10px] text-purple-400 bg-purple-400/10 px-1.5 py-0.5 rounded">{v.cve}</span>}
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-xs text-shark-muted mb-2">
                    <span>目标: {v.target || '—'}</span>
                    <span>位置: {v.endpoint || '—'}</span>
                    <span>工具: {v.foundBy || '—'}</span>
                  </div>
                  {v.description && <p className="text-xs text-shark-muted mb-2">{v.description}</p>}
                  {v.recommendation && (
                    <div className="text-xs text-emerald-400/80 p-2 rounded bg-emerald-400/5 border border-emerald-400/10">
                      <span className="font-medium">修复建议：</span>{v.recommendation}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: number; color: string }) {
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
