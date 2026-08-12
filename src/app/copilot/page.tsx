'use client'

import { useState } from 'react'
import { Bot, Send, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

const API = ''

interface Message { role: 'user' | 'assistant'; content: string }

export default function CopilotPage() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '你好！我是 BestNative AI 助手。可以帮你：\n• 查询服务状态和拓扑\n• 分析告警根因\n• 执行安全扫描\n• 查看部署记录\n• 推荐运维优化\n\n输入你的问题开始。' },
  ])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)

  const send = async () => {
    if (!input.trim() || sending) return
    const q = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: q }])
    setSending(true)
    try {
      const res = await fetch(`${API}/api/health`)
      const health = await res.json()
      // 简单搜索已有数据来回答（后续接 LangChain agent）
      let reply = ''
      if (q.includes('服务') || q.includes('拓扑')) {
        const tRes = await fetch(`${API}/api/topology/graph`)
        const t = await tRes.json()
        const nodes = t?.nodes || []
        reply = `当前共发现 **${nodes.length}** 个资源：\n${nodes.map((n: { name: string; type: string; health: string }) => `- ${n.type}: **${n.name}** (${n.health})`).slice(0, 10).join('\n')}${nodes.length > 10 ? `\n... 等 ${nodes.length - 10} 个` : ''}`
      } else if (q.includes('告警') || q.includes('事件')) {
        const iRes = await fetch(`${API}/api/incidents?limit=5`)
        const incs = await iRes.json()
        reply = Array.isArray(incs) && incs.length > 0
          ? `当前活跃事件 ${incs.length} 个：\n${incs.map((i: { title: string; severity: string; status: string }) => `- [${i.severity}] ${i.title} (${i.status})`).join('\n')}`
          : '当前无活跃事件。✅'
      } else if (q.includes('安全') || q.includes('漏洞') || q.includes('扫描')) {
        const sRes = await fetch(`${API}/api/security/stats`)
        const s = await sRes.json()
        reply = `安全概况：总扫描 ${s.totalScans} 次，漏洞 ${Object.entries(s.bySeverity || {}).map(([k,v]) => `${k}:${v}`).join(' / ')}`
      } else if (q.includes('发布') || q.includes('部署')) {
        const dRes = await fetch(`${API}/api/deployments?limit=3`)
        const deps = await dRes.json()
        reply = Array.isArray(deps) && deps.length > 0
          ? `最近发布：\n${deps.map((d: { service: string; version: string; status: string }) => `- ${d.service} → ${d.version} (${d.status})`).join('\n')}`
          : '暂无发布记录。'
      } else if (q.includes('环境')) {
        reply = `当前环境: **${health.environment}**\n版本: ${health.version}\n状态: ${health.status}`
      } else {
        reply = `收到。你可以试试问：\n• "查看当前服务拓扑"\n• "最近有什么告警"\n• "运行安全扫描"\n• "最近的部署情况"\n• "当前环境信息"`
      }
      setMessages(prev => [...prev, { role: 'assistant', content: reply }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '抱歉，无法连接到 API 服务。请检查后端是否运行。' }])
    } finally { setSending(false) }
  }

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2"><Bot size={16} className="text-purple-400" /> AI 助手</h1>
        <span className="ml-3 text-xs text-shark-muted">基于 DeepSeek · 实时查询运维数据</span>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-3xl mx-auto space-y-4">
          {messages.map((m, i) => (
            <div key={i} className={cn('flex gap-3', m.role === 'user' ? 'justify-end' : '')}>
              {m.role === 'assistant' && <div className="w-8 h-8 rounded-full bg-purple-400/10 flex items-center justify-center shrink-0 mt-1"><Bot size={16} className="text-purple-400" /></div>}
              <div className={cn('rounded-xl px-4 py-3 max-w-[80%] whitespace-pre-wrap text-sm leading-relaxed',
                m.role === 'user' ? 'bg-shark-accent/20 border border-shark-accent/30 text-white' : 'glass border border-shark-border text-shark-text'
              )}>
                {m.content.split(/(\*\*.*?\*\*)/).map((part, j) =>
                  part.startsWith('**') && part.endsWith('**')
                    ? <strong key={j} className="text-white">{part.slice(2, -2)}</strong>
                    : part
                )}
              </div>
            </div>
          ))}
          {sending && <div className="flex items-center gap-2 text-shark-muted text-sm"><Loader2 size={14} className="animate-spin" /> 思考中...</div>}
        </div>
      </div>

      <div className="shrink-0 glass border-t border-shark-border px-6 py-4">
        <div className="max-w-3xl mx-auto flex gap-3">
          <input value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
            placeholder='试试："查看当前服务拓扑" / "最近有什么告警" / "运行安全扫描"'
            className="flex-1 bg-shark-bg border border-shark-border rounded-xl px-4 py-2.5 text-sm text-white placeholder-shark-muted/50 outline-none focus:border-shark-accent"
          />
          <button onClick={send} disabled={sending || !input.trim()}
            className="px-4 py-2.5 bg-shark-accent/20 border border-shark-accent/30 text-shark-accent rounded-xl hover:bg-shark-accent/30 transition-colors disabled:opacity-50">
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
