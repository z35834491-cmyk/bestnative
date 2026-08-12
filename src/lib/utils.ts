import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function fmtTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diffMin = Math.floor((now.getTime() - d.getTime()) / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `${diffH}小时前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

export const healthColor: Record<string, string> = {
  healthy: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/30',
  degraded: 'text-amber-400 bg-amber-400/10 border-amber-400/30',
  critical: 'text-red-400 bg-red-400/10 border-red-400/30',
  unknown: 'text-slate-400 bg-slate-400/10 border-slate-400/30',
}

export const healthDot: Record<string, string> = {
  healthy: 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]',
  degraded: 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.5)]',
  critical: 'bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.5)]',
  unknown: 'bg-slate-500',
}

export const severityColor: Record<string, string> = {
  critical: 'text-red-400 bg-red-400/10',
  warning: 'text-amber-400 bg-amber-400/10',
  info: 'text-blue-400 bg-blue-400/10',
}

export const severityBadge: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400 border-red-500/30',
  warning: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  info: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
}
