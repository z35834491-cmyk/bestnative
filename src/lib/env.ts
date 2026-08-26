const ENV_KEY = 'shore_active_env'

export function getActiveEnvId(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(ENV_KEY)
}

export function setActiveEnvId(id: string) {
  localStorage.setItem(ENV_KEY, id)
}

export interface EnvironmentItem {
  id: string
  label: string
  clusterName: string
  kubeconfigConfigured?: boolean
  prometheusUrl?: string
  esHost?: string
}
