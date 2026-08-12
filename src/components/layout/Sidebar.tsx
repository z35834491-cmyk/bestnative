'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard, GitFork, AlertTriangle, BarChart3,
  BookOpen, ClipboardCheck, Calendar, DollarSign,
  Shield, Settings, Bot, ChevronLeft, ChevronRight, Rocket,
} from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { href: '/', label: '全局总览', icon: LayoutDashboard },
  { href: '/topology', label: '服务拓扑', icon: GitFork },
  { href: '/incidents', label: '事件中心', icon: AlertTriangle },
  { href: '/deployments', label: '发布管理', icon: Rocket },
  { href: '/monitoring', label: '监控面板', icon: BarChart3 },
  { href: '/knowledge', label: '知识库', icon: BookOpen },
  { href: '/inspections', label: '巡检报告', icon: ClipboardCheck },
  { href: '/schedules', label: '排班管理', icon: Calendar },
  { href: '/cost', label: '成本分析', icon: DollarSign },
  { href: '/security', label: '安全合规', icon: Shield },
  { href: '/settings', label: '平台设置', icon: Settings },
]

export default function AppSidebar() {
  const pathname = usePathname()
  const [collapsed, setCollapsed] = useState(false)

  return (
    <aside className={cn(
      'h-screen flex flex-col bg-shark-card border-r border-shark-border transition-all duration-300',
      collapsed ? 'w-[68px]' : 'w-[240px]'
    )}>
      {/* Logo */}
      <div className="h-16 flex items-center px-5 border-b border-shark-border shrink-0">
        <div className="w-8 h-8 rounded-lg bg-shark-accent/20 flex items-center justify-center shrink-0">
          <span className="text-shark-accent font-bold text-sm">BN</span>
        </div>
        {!collapsed && (
          <span className="ml-3 font-bold text-white text-base whitespace-nowrap">BestNative</span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 overflow-y-auto">
        {!collapsed && (
          <div className="px-5 mb-2 text-[11px] font-semibold text-shark-muted uppercase tracking-wider">
            导航
          </div>
        )}
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                'mx-3 mb-1 flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
                active
                  ? 'bg-gradient-to-r from-shark-accent to-shark-accent-hover text-white shadow-lg shadow-shark-accent/25'
                  : 'text-shark-muted hover:bg-white/5 hover:text-white'
              )}
            >
              <Icon size={18} className="shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          )
        })}
      </nav>

      {/* AI button */}
      <div className="px-3 pb-3">
        <Link
          href="/copilot"
          className={cn(
            'flex items-center gap-3 px-3 py-2.5 rounded-lg bg-gradient-to-r from-purple-500/20 to-blue-500/20 border border-purple-500/20 hover:border-purple-400/40 transition-all',
            collapsed && 'justify-center'
          )}
        >
          <Bot size={18} className="text-purple-400 shrink-0" />
          {!collapsed && <span className="text-purple-300 font-medium text-sm">AI 助手</span>}
        </Link>
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="h-12 flex items-center justify-center border-t border-shark-border text-shark-muted hover:text-white transition-colors"
      >
        {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
      </button>
    </aside>
  )
}
