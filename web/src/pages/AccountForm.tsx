import { useState, type FormEvent } from 'react'
import { useCreateAccount } from '../api/queries'
import { ApiError } from '../api/http'
import type { Account } from '../api/types'

const SERVER_TIME_SUGGESTIONS = ['ny_close', 'UTC', 'Europe/London', 'Europe/Athens', 'Europe/Zurich']

export function AccountForm({
  onCreated,
  onCancel,
}: {
  onCreated: (account: Account) => void
  onCancel: () => void
}) {
  const create = useCreateAccount()
  const [label, setLabel] = useState('')
  const [broker, setBroker] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [balance, setBalance] = useState('0')
  const [serverTime, setServerTime] = useState('')
  const [isDemo, setIsDemo] = useState(false)

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      {
        label: label.trim(),
        broker: broker.trim() || null,
        currency: currency.trim().toUpperCase(),
        starting_balance: balance.trim() || '0',
        is_demo: isDemo,
        server_timezone: serverTime.trim() || null,
      },
      { onSuccess: onCreated },
    )
  }

  const error =
    create.error instanceof ApiError ? create.error.message : create.error ? 'Could not create the account.' : null

  return (
    <form onSubmit={submit} className="card form" aria-label="New account">
      <h2>New account</h2>
      <label>
        Name
        <input required maxLength={100} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="IFX Demo" />
      </label>
      <label>
        Broker (optional)
        <input maxLength={100} value={broker} onChange={(e) => setBroker(e.target.value)} />
      </label>
      <div className="row">
        <label>
          Currency
          <input
            required
            pattern="[A-Za-z]{3}"
            title="A 3-letter currency code, e.g. USD"
            maxLength={3}
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          />
        </label>
        <label>
          Starting balance
          <input
            inputMode="decimal"
            pattern="[0-9]+(\.[0-9]{1,2})?"
            title="A number with up to 2 decimals"
            value={balance}
            onChange={(e) => setBalance(e.target.value)}
          />
        </label>
      </div>
      <label>
        Broker server time (optional)
        <input
          list="server-times"
          value={serverTime}
          onChange={(e) => setServerTime(e.target.value)}
          placeholder="ny_close or an IANA zone"
        />
        <datalist id="server-times">
          {SERVER_TIME_SUGGESTIONS.map((zone) => (
            <option key={zone} value={zone} />
          ))}
        </datalist>
        <span className="hint">
          How to read the times in MT5 reports. <code>ny_close</code> means New York + 7 hours.
        </span>
      </label>
      <label className="check">
        <input type="checkbox" checked={isDemo} onChange={(e) => setIsDemo(e.target.checked)} />
        Demo account
      </label>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="row actions">
        <button type="submit" className="button" disabled={create.isPending}>
          {create.isPending ? 'Creating…' : 'Create account'}
        </button>
        <button type="button" className="button secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
