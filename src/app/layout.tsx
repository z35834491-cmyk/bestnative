import type { Metadata } from 'next'
import './globals.css'
import AppSidebar from '@/components/layout/Sidebar'

export const metadata: Metadata = {
  title: 'BestNative — AI-Native 运维指挥中心',
  description: '全栈可观测运维平台',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="dark">
      <body className="bg-shark-bg text-shark-text antialiased">
        <div className="flex h-screen overflow-hidden">
          <AppSidebar />
          <main className="flex-1 overflow-auto">
            {children}
          </main>
        </div>
      </body>
    </html>
  )
}
