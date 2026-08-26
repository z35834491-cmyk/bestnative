'use client'

import { Loader2, WifiOff } from 'lucide-react'

export function LoadingSpinner({ size = 32 }: { size?: number }) {
  return (
    <div className="h-full flex items-center justify-center">
      <Loader2 size={size} className="animate-spin text-shark-accent" />
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center space-y-3">
        <WifiOff size={40} className="text-red-400 mx-auto" />
        <p className="text-sm text-shark-muted">{message}</p>
        {onRetry && (
          <button onClick={onRetry} className="text-xs text-shark-accent border border-shark-accent/30 px-3 py-1.5 rounded">
            重试
          </button>
        )}
      </div>
    </div>
  )
}
