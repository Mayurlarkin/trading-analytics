import { useEffect, useState } from 'react'
import { fetchSystemHealth, type SystemHealth } from '../api/health'

export function SystemStatus() {
  const [health, setHealth] = useState<SystemHealth | null>(null)

  useEffect(() => {
    let cancelled = false
    void fetchSystemHealth().then((result) => {
      if (!cancelled) setHealth(result)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section aria-label="System status" className="status">
      <h2 className="visually-hidden">System status</h2>
      {health === null ? (
        <p>Checking…</p>
      ) : (
        <ul>
          <li>
            API: <strong data-status={health.api}>{health.api}</strong>
          </li>
          <li>
            Database: <strong data-status={health.database}>{health.database}</strong>
          </li>
        </ul>
      )}
    </section>
  )
}
