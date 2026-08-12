'use client'

import { useState } from 'react'
import { Calendar, Clock, User, Phone, Plus, X } from 'lucide-react'

interface Shift {
  id: string; user: string; date: string; phone: string; role: 'primary' | 'secondary'
}

const DUTY_USERS = ['张三 (SRE)', '李四 (Backend)', '王五 (Platform)', '赵六 (Network)']

export default function SchedulesPage() {
  const [shifts, setShifts] = useState<Shift[]>([
    { id: '1', user: '张三 (SRE)', date: '2026-08-11', phone: '080-1234-0001', role: 'primary' },
    { id: '2', user: '李四 (Backend)', date: '2026-08-11', phone: '080-1234-0002', role: 'secondary' },
    { id: '3', user: '王五 (Platform)', date: '2026-08-12', phone: '080-1234-0003', role: 'primary' },
    { id: '4', user: '赵六 (Network)', date: '2026-08-12', phone: '080-1234-0004', role: 'secondary' },
  ])
  const [showAdd, setShowAdd] = useState(false)
  const [newUser, setNewUser] = useState(DUTY_USERS[0])
  const [newDate, setNewDate] = useState('')
  const [newPhone, setNewPhone] = useState('')
  const [newRole, setNewRole] = useState<'primary'|'secondary'>('primary')

  const add = () => {
    if (!newDate) return
    setShifts(prev => [...prev, { id: String(Date.now()), user: newUser, date: newDate, phone: newPhone, role: newRole }])
    setShowAdd(false)
  }

  const remove = (id: string) => setShifts(prev => prev.filter(s => s.id !== id))

  const grouped: Record<string, Shift[]> = {}
  for (const s of shifts.sort((a, b) => a.date.localeCompare(b.date))) {
    (grouped[s.date] ||= []).push(s)
  }

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2"><Calendar size={16} className="text-blue-400" /> 排班管理</h1>
        <button onClick={() => setShowAdd(true)} className="ml-auto flex items-center gap-1 text-xs text-shark-accent border border-shark-accent/30 px-3 py-1.5 rounded hover:bg-shark-accent/10 transition-colors">
          <Plus size={14} /> 添加值班
        </button>
      </header>

      <div className="flex-1 overflow-auto p-6">
        {/* Add dialog */}
        {showAdd && (
          <div className="mb-6 glass rounded-xl p-5 border border-shark-accent/20">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-white">添加值班</h3>
              <button onClick={() => setShowAdd(false)} className="text-shark-muted hover:text-white"><X size={16} /></button>
            </div>
            <div className="grid grid-cols-4 gap-3">
              <select value={newUser} onChange={e => setNewUser(e.target.value)} className="bg-shark-bg border border-shark-border rounded-lg px-3 py-2 text-sm text-white">
                {DUTY_USERS.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
              <input value={newDate} onChange={e => setNewDate(e.target.value)} type="date" className="bg-shark-bg border border-shark-border rounded-lg px-3 py-2 text-sm text-white" />
              <input value={newPhone} onChange={e => setNewPhone(e.target.value)} placeholder="电话号码" className="bg-shark-bg border border-shark-border rounded-lg px-3 py-2 text-sm text-white placeholder-shark-muted/50" />
              <div className="flex gap-2">
                <select value={newRole} onChange={e => setNewRole(e.target.value as 'primary'|'secondary')} className="flex-1 bg-shark-bg border border-shark-border rounded-lg px-3 py-2 text-sm text-white">
                  <option value="primary">主值班</option>
                  <option value="secondary">备值班</option>
                </select>
                <button onClick={add} className="px-4 py-2 bg-shark-accent/20 border border-shark-accent/30 text-shark-accent text-sm rounded-lg hover:bg-shark-accent/30">确认</button>
              </div>
            </div>
          </div>
        )}

        {Object.keys(grouped).length === 0 && <p className="text-sm text-shark-muted">暂无排班数据</p>}

        <div className="space-y-4">
          {Object.entries(grouped).map(([date, shifts]) => (
            <div key={date} className="glass rounded-xl p-5">
              <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
                <Clock size={14} className="text-blue-400" />
                {date}
              </h3>
              <div className="space-y-2">
                {shifts.map(s => (
                  <div key={s.id} className="flex items-center justify-between p-3 rounded-lg border border-shark-border bg-shark-card/30">
                    <div className="flex items-center gap-3">
                      <User size={16} className={s.role === 'primary' ? 'text-amber-400' : 'text-shark-muted'} />
                      <div>
                        <p className="text-sm text-white font-medium">{s.user}</p>
                        <p className="text-xs text-shark-muted">{s.role === 'primary' ? '主值班 · 告警第一通知人' : '备值班 · 告警第二通知人'}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-xs text-shark-muted flex items-center gap-1"><Phone size={12} /> {s.phone || '未设置'}</span>
                      <button onClick={() => remove(s.id)} className="text-shark-muted hover:text-red-400 transition-colors"><X size={14} /></button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
