'use client'

import { useCallback, useEffect, useState } from 'react'
import { Calendar, Loader2, Plus, Trash2, User } from 'lucide-react'
import { apiJson } from '@/lib/api'
import { ErrorState, LoadingSpinner } from '@/components/ui/AsyncState'
import { fmtTime } from '@/lib/utils'

interface ScheduleRow {
  id: string
  userId: string
  userName: string
  shiftDate: string
  shiftType: string
  note: string
}

interface UserRow {
  id: string
  username: string
  displayName: string
}

export default function SchedulesPage() {
  const [rows, setRows] = useState<ScheduleRow[]>([])
  const [users, setUsers] = useState<UserRow[]>([])
  const [onCall, setOnCall] = useState<ScheduleRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [userId, setUserId] = useState('')
  const [shiftDate, setShiftDate] = useState('')
  const [shiftType, setShiftType] = useState('day')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [schedules, userList, onCallData] = await Promise.all([
        apiJson<ScheduleRow[]>('/api/ops/schedules'),
        apiJson<UserRow[]>('/api/ops/users'),
        apiJson<{ shifts: ScheduleRow[] }>('/api/ops/schedules/on-call'),
      ])
      setRows(schedules)
      setUsers(userList)
      setOnCall(onCallData.shifts || [])
      if (!userId && userList[0]) setUserId(userList[0].id)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => { fetchAll() }, [fetchAll])

  const addSchedule = async () => {
    if (!userId || !shiftDate) return
    setSaving(true)
    try {
      await apiJson('/api/ops/schedules', {
        method: 'POST',
        body: JSON.stringify({ userId, shiftDate: new Date(shiftDate).toISOString(), shiftType, note }),
      })
      setNote('')
      await fetchAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (id: string) => {
    try {
      await apiJson(`/api/ops/schedules/${id}`, { method: 'DELETE' })
      await fetchAll()
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败')
    }
  }

  return (
    <div className="h-full flex flex-col">
      <header className="shrink-0 glass border-b border-shark-border flex items-center px-6 h-14">
        <h1 className="text-sm font-semibold text-white flex items-center gap-2">
          <Calendar size={16} className="text-violet-400" /> 值班排班
        </h1>
      </header>

      <div className="flex-1 overflow-auto p-6 space-y-6 max-w-4xl">
        {loading && <LoadingSpinner />}
        {error && <ErrorState message={error} onRetry={fetchAll} />}

        {!loading && onCall.length > 0 && (
          <div className="glass rounded-xl p-4 border border-shark-accent/30">
            <div className="text-xs text-shark-accent font-medium mb-2 flex items-center gap-1"><User size={12} /> 近期值班</div>
            {onCall.map(s => (
              <div key={s.userId + s.shiftDate} className="text-sm text-white">
                {s.userName} · {s.shiftType} · {fmtTime(s.shiftDate)}
              </div>
            ))}
          </div>
        )}

        <div className="glass rounded-xl p-5 border border-shark-border space-y-3">
          <h2 className="text-xs font-semibold text-shark-muted uppercase">添加排班</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <select value={userId} onChange={e => setUserId(e.target.value)}
              className="bg-shark-bg border border-shark-border rounded-lg px-3 py-2 text-xs text-white">
              {users.map(u => <option key={u.id} value={u.id}>{u.displayName}</option>)}
            </select>
            <input type="datetime-local" value={shiftDate} onChange={e => setShiftDate(e.target.value)}
              className="bg-shark-bg border border-shark-border rounded-lg px-3 py-2 text-xs text-white" />
            <select value={shiftType} onChange={e => setShiftType(e.target.value)}
              className="bg-shark-bg border border-shark-border rounded-lg px-3 py-2 text-xs text-white">
              <option value="day">白班</option>
              <option value="night">夜班</option>
              <option value="full">全天</option>
            </select>
            <input value={note} onChange={e => setNote(e.target.value)} placeholder="备注"
              className="bg-shark-bg border border-shark-border rounded-lg px-3 py-2 text-xs text-white" />
          </div>
          <button onClick={addSchedule} disabled={saving || !shiftDate}
            className="text-xs bg-shark-accent text-white px-4 py-2 rounded-lg flex items-center gap-1 disabled:opacity-50">
            {saving ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} 添加
          </button>
        </div>

        <section className="space-y-2">
          {rows.map(r => (
            <div key={r.id} className="glass rounded-lg px-4 py-3 border border-shark-border flex items-center gap-3 text-xs">
              <span className="text-white font-medium w-24">{r.userName}</span>
              <span className="text-shark-muted">{fmtTime(r.shiftDate)}</span>
              <span className="text-shark-accent border border-shark-accent/20 px-1.5 py-0.5 rounded">{r.shiftType}</span>
              <span className="text-shark-muted flex-1 truncate">{r.note}</span>
              <button onClick={() => remove(r.id)} className="text-red-400/80 hover:text-red-400"><Trash2 size={14} /></button>
            </div>
          ))}
        </section>
      </div>
    </div>
  )
}
