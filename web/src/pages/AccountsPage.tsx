import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAccounts } from '../api/queries'
import { formatDate, formatMoney } from '../lib/format'
import { AccountForm } from './AccountForm'

export function AccountsPage() {
  const accounts = useAccounts()
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)

  return (
    <>
      <div className="page-head">
        <h1>Accounts</h1>
        {!creating && (
          <button type="button" className="button" onClick={() => setCreating(true)}>
            New account
          </button>
        )}
      </div>

      {creating && (
        <AccountForm
          onCancel={() => setCreating(false)}
          onCreated={(account) => void navigate(`/accounts/${account.id}`)}
        />
      )}

      {accounts.isPending && <p className="muted">Loading accounts…</p>}
      {accounts.isError && (
        <p role="alert" className="error">
          Could not load your accounts: {accounts.error.message}
        </p>
      )}

      {accounts.data && accounts.data.length === 0 && !creating && (
        <div className="card empty">
          <h2>No accounts yet</h2>
          <p>
            An account is one trading account at a broker. Create one, then bring its trades in
            with an MT5 report or the reporter EA.
          </p>
          <button type="button" className="button" onClick={() => setCreating(true)}>
            Create your first account
          </button>
        </div>
      )}

      {accounts.data && accounts.data.length > 0 && (
        <ul className="account-list">
          {accounts.data.map((account) => (
            <li key={account.id} className="card">
              <div className="account-main">
                <h2>
                  <Link to={`/accounts/${account.id}`}>{account.label}</Link>
                </h2>
                <p className="muted">
                  {[account.broker, account.is_demo ? 'Demo' : 'Live', account.currency]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              </div>
              <dl className="account-facts">
                <div>
                  <dt>Trades</dt>
                  <dd>{account.trade_count}</dd>
                </div>
                <div>
                  <dt>Starting balance</dt>
                  <dd>
                    {formatMoney(account.starting_balance)} {account.currency}
                  </dd>
                </div>
                <div>
                  <dt>Last trade closed</dt>
                  <dd>{formatDate(account.last_close_time)}</dd>
                </div>
              </dl>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
