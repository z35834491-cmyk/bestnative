'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard, GitFork, AlertTriangle, BookOpen,
  Shield, Settings, Rocket, FileText, ChevronLeft, ChevronRight, Boxes,
  Activity, DollarSign, Calendar, Bot,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth'
import { useEnvironments } from '@/lib/useEnvironments'

const navItems = [
  { href: '/', label: '全局总览', icon: LayoutDashboard },
  { href: '/topology', label: '服务拓扑', icon: GitFork },
  { href: '/incidents', label: '事件中心', icon: AlertTriangle },
  { href: '/pods', label: 'Pod 管理', icon: Boxes },
  { href: '/deployments', label: '发布管理', icon: Rocket },
  { href: '/logs', label: '日志监控', icon: FileText },
  { href: '/monitoring', label: '监控巡检', icon: Activity },
  { href: '/cost', label: '成本分析', icon: DollarSign },
  { href: '/schedules', label: '值班排班', icon: Calendar },
  { href: '/copilot', label: '运维助手', icon: Bot },
  { href: '/knowledge', label: '知识库', icon: BookOpen },
  { href: '/settings', label: '平台设置', icon: Settings },
]

export default function AppSidebar() {
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const { environments, active, switchEnv } = useEnvironments()
  const [collapsed, setCollapsed] = useState(false)

  if (pathname === '/login') return null

  return (
    <aside className={cn(
      'h-screen flex flex-col bg-shark-card border-r border-shark-border transition-all duration-300',
      collapsed ? 'w-[68px]' : 'w-[240px]'
    )}>
      <div className="h-16 flex items-center px-5 border-b border-shark-border shrink-0">
        <div className="w-8 h-8 rounded-lg bg-shark-accent/20 flex items-center justify-center shrink-0">
          <span className="text-shark-accent font-bold text-sm">SH</span>
        </div>
        {!collapsed && <span className="ml-3 font-bold text-white text-base whitespace-nowrap">Shore</span>}
      </div>

      {!collapsed && environments.length > 1 && (
        <div className="px-4 py-3 border-b border-shark-border">
          <label className="text-[10px] text-shark-muted uppercase tracking-wider">环境</label>
          <select
            value={active}
            onChange={e => switchEnv(e.target.value)}
            className="mt-1 w-full bg-shark-bg border border-shark-border rounded-lg px-2 py-1.5 text-xs text-white"
          >
            {environments.map(env => (
              <option key={env.id} value={env.id}>{env.label} ({env.clusterName})</option>
            ))}
          </select>
        </div>
      )}

      <nav className="flex-1 py-4 overflow-y-auto">
        {!collapsed && <div className="px-5 mb-2 text-[11px] font-semibold text-shark-muted uppercase tracking-wider">导航</div>}
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || (href !== '/' && pathname.startsWith(href))
          return (
            <Link key={href} href={href}
              className={cn('mx-3 mb-1 flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
                active ? 'bg-gradient-to-r from-shark-accent to-shark-accent-hover text-white shadow-lg shadow-shark-accent/25'
                  : 'text-shark-muted hover:bg-white/5 hover:text-white')}>
              <Icon size={18} className="shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          )
        })}
        <Link href="/security"
          className={cn('mx-3 mb-1 flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
            pathname.startsWith('/security') ? 'bg-white/10 text-white' : 'text-shark-muted hover:bg-white/5 hover:text-white')}>
          <Shield size={18} className="shrink-0" />
          {!collapsed && <span className="truncate">安全合规</span>}
        </Link>
      </nav>

      <div className="px-3 pb-3 text-[10px] text-shark-muted">
        {!collapsed && user && (
          <div className="mb-2 px-2">
            <div className="text-white truncate">{user.displayName || user.username}</div>
            <button onClick={logout} className="text-shark-accent hover:underline">退出</button>
          </div>
        )}
      </div>

      <button onClick={() => setCollapsed(!collapsed)}
        className="h-12 flex items-center justify-center border-t border-shark-border text-shark-muted hover:text-white">
        {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
      </button>
    </aside>
  )
}
