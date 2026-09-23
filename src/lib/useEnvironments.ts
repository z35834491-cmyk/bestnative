'use client'

import { useCallback, useEffect, useState } from 'react'
import { apiJson } from '@/lib/api'
import { EnvironmentItem, getActiveEnvId, setActiveEnvId } from '@/lib/env'

export function useEnvironments() {
  const [environments, setEnvironments] = useState<EnvironmentItem[]>([])
  const [active, setActive] = useState<string>(() => getActiveEnvId() || '')

  const load = useCallback(async () => {
    const data = await apiJson<{ active: string; environments: EnvironmentItem[] }>('/api/settings/environments')
    setEnvironments(data.environments || [])
    const next = getActiveEnvId() || data.active
    setActive(next)
    if (next) setActiveEnvId(next)
  }, [])

  useEffect(() => { load().catch(() => {}) }, [load])

  const switchEnv = useCallback(async (id: string) => {
    setActiveEnvId(id)
    setActive(id)
    try {
      await apiJson('/api/settings/environments/active', {
        method: 'PUT',
        body: JSON.stringify({ id }),
      })
    } catch {
      // 非 admin 或未配 Redis 时仍靠 localStorage + 请求头切换
    }
    window.location.reload()
  }, [])

  return { environments, active, switchEnv, reload: load }
}
