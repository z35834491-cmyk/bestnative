'use client'

import { useCallback, useRef, useState } from 'react'
import { Bot, Loader2, Send } from 'lucide-react'
import { apiJson } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export default function CopilotPage() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '我是 Shore 运维助手。可以帮你查服务状态、指标、日志、事件和知识库。' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return
    const next: Message[] = [...messages, { role: 'user', content: text }]
    setMessages(next)
    setInput('')
    setLoading(true)
    try {
      const history = next.slice(0, -1).map(m => ({ role: m.role, content: m.content }))
      const res = await apiJson<{ reply: string }>('/api/ops/copilot/chat', {
        method: 'POST',
        body: JSON.stringify({ message: text, history }),
      })
      setMessages([...next, { role: 'assistant', content: res.reply || '（无回复）' }])
    } catch (e) {
      setMessages([...next, { role: 'assistant', content: e instanceof Error ? e.message : '请求失败' }])
    } finally {
      setLoading(false)
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    }
  }, [input, loading, messages])

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2">
          <Bot size={16} className="text-cyan-400" /> 运维助手
        </h1>
      </header>

      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-3xl mx-auto space-y-4">
          {messages.map((m, i) => (
            <div key={i} className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
              <div className={cn(
                'max-w-[85%] rounded-xl px-4 py-3 text-sm whitespace-pre-wrap',
                m.role === 'user'
                  ? 'bg-shark-accent/20 text-white border border-shark-accent/30'
                  : 'glass border border-shark-border text-shark-muted',
              )}>
                {m.content}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex items-center gap-2 text-shark-muted text-xs">
              <Loader2 size={14} className="animate-spin" /> 思考中…
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="shrink-0 border-t border-shark-border p-4">
        <div className="max-w-3xl mx-auto flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), send())}
            placeholder="问：exchange-gateway 最近有告警吗？test 环境 CPU 怎么样？"
            className="flex-1 bg-shark-bg border border-shark-border rounded-xl px-4 py-3 text-sm text-white outline-none focus:border-shark-accent"
          />
          <button onClick={send} disabled={loading || !input.trim()}
            className="bg-shark-accent text-white px-4 rounded-xl disabled:opacity-50">
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
