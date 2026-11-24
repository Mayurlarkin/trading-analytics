import { Link, NavLink, Outlet } from 'react-router-dom'
import { useMe } from '../api/queries'
import { useAuth } from '../auth/useAuth'
import { SystemStatus } from './SystemStatus'

export function Layout() {
  const { logout } = useAuth()
  const me = useMe()

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          Trading Analytics
        </Link>
        <nav aria-label="Main">
          <NavLink to="/" end>
            Accounts
          </NavLink>
        </nav>
        <div className="topbar-user">
          {me.data && <span className="muted">{me.data.email}</span>}
          <button type="button" className="button secondary" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
      <footer className="footer">
        <SystemStatus />
        <p className="muted small">Not financial advice. Past results do not predict future ones.</p>
      </footer>
    </div>
  )
}
