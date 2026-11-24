import { API_URL } from './http'

export type HealthStatus = 'up' | 'down'

export interface SystemHealth {
  api: HealthStatus
  database: HealthStatus
}

async function isOk(path: string): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}${path}`)
    return response.ok
  } catch {
    return false
  }
}

export async function fetchSystemHealth(): Promise<SystemHealth> {
  const [api, database] = await Promise.all([isOk('/health'), isOk('/health/db')])
  return {
    api: api ? 'up' : 'down',
    database: database ? 'up' : 'down',
  }
}
