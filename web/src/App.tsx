import { useEffect, useState } from 'react'
import { fetchSystemHealth, type SystemHealth } from './api'

function App() {
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
    <main className="app">
      <h1>Trading Analytics</h1>
      <p className="tagline">Trade history in, performance insight out.</p>

      <section aria-label="System status" className="status">
        <h2>System status</h2>
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
    </main>
  )
}

export default App
