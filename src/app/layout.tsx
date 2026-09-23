import type { Metadata } from 'next'
import './globals.css'
import AppSidebar from '@/components/layout/Sidebar'
import { Providers } from '@/components/Providers'

export const metadata: Metadata = {
  title: 'Shore — AIOps',
  description: 'AIOps 控制面 · 10 Agent · 告警诊断 · 发布观测 · 巡检 · RAG · Copilot',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <body className="bg-shark-bg text-shark-text antialiased">
        <Providers>
          <div className="flex h-screen overflow-hidden">
            <AppSidebar />
            <main className="flex-1 overflow-auto">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  )
}
