import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ACCOUNT, SUMMARY, curve } from './test/fixtures'
import { HEALTH, mockApi, renderApp } from './test/helpers'

const ME = { id: 1, email: 'trader@example.com' }

function loggedInApi(extra: Record<string, unknown> = {}) {
  return mockApi({
    ...HEALTH,
    'GET /auth/me': ME,
    'GET /accounts': [ACCOUNT],
    'GET /accounts/1': ACCOUNT,
    'GET /accounts/1/summary': SUMMARY,
    'GET /accounts/1/equity-curve': curve(),
    ...extra,
  })
}

describe('logging in', () => {
  it('sends someone without a login to the login page, without asking for any data', async () => {
    const { calls } = loggedInApi()
    renderApp('/accounts/1', { token: null })
    expect(await screen.findByRole('form', { name: 'Log in' })).toBeInTheDocument()
    expect(calls.filter((c) => c.path.startsWith('/accounts'))).toEqual([])
  })

  it('logs in, then shows the accounts and sends the token on later requests', async () => {
    const { calls } = loggedInApi({
      'POST /auth/login': { body: { access_token: 'fresh-token', token_type: 'bearer', expires_in: 28800 } },
    })
    renderApp('/login', { token: null })
    const user = userEvent.setup()

    await user.type(screen.getByLabelText('Email'), 'trader@example.com')
    await user.type(screen.getByLabelText('Password'), 'correct-horse-battery')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('heading', { name: 'Accounts' })).toBeInTheDocument()
    const login = calls.find((c) => c.path === '/auth/login')!
    expect(new URLSearchParams(login.body!).get('username')).toBe('trader@example.com')
    expect(new URLSearchParams(login.body!).get('password')).toBe('correct-horse-battery')
    expect(login.headers.Authorization).toBeUndefined()
    const accounts = calls.find((c) => c.path === '/accounts')!
    expect(accounts.headers.Authorization).toBe('Bearer fresh-token')
    expect(sessionStorage.getItem('ta.token')).toBe('fresh-token')
  })

  it('goes back to the page that was asked for after logging in', async () => {
    loggedInApi({
      'POST /auth/login': { body: { access_token: 't', token_type: 'bearer', expires_in: 1 } },
    })
    renderApp('/accounts/1', { token: null })
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Email'), 'trader@example.com')
    await user.type(screen.getByLabelText('Password'), 'correct-horse-battery')
    await user.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('heading', { name: 'Demo account' })).toBeInTheDocument()
  })

  it('shows the API message for a wrong password and stays on the page', async () => {
    loggedInApi({
      'POST /auth/login': { status: 401, body: { detail: 'incorrect email or password' } },
    })
    renderApp('/login', { token: null })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'trader@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('incorrect email or password')
    expect(screen.getByRole('button', { name: 'Log in' })).toBeEnabled()
    expect(sessionStorage.getItem('ta.token')).toBeNull()
  })

  it('says so when the API cannot be reached', async () => {
    const { fetchMock } = loggedInApi()
    fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')))
    renderApp('/login', { token: null })
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('Email'), 'a@b.co')
    await user.type(screen.getByLabelText('Password'), 'whatever-pass')
    await user.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/cannot reach the api/i)
  })

  it('logs out when the API says the token is no longer valid', async () => {
    loggedInApi({
      'GET /accounts': { status: 401, body: { detail: 'not authenticated' } },
      'GET /auth/me': { status: 401, body: { detail: 'not authenticated' } },
    })
    sessionStorage.setItem('ta.token', 'expired')
    renderApp('/', { token: 'expired' })
    expect(await screen.findByRole('form', { name: 'Log in' })).toBeInTheDocument()
    expect(sessionStorage.getItem('ta.token')).toBeNull()
  })

  it('log out clears the token and returns to the login page', async () => {
    loggedInApi()
    sessionStorage.setItem('ta.token', 'test-token')
    renderApp('/')
    const user = userEvent.setup()
    expect(await screen.findByText('trader@example.com')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Log out' }))
    expect(await screen.findByRole('form', { name: 'Log in' })).toBeInTheDocument()
    expect(sessionStorage.getItem('ta.token')).toBeNull()
  })

  it('does not show the login page to someone who is already logged in', async () => {
    loggedInApi()
    renderApp('/login')
    expect(await screen.findByRole('heading', { name: 'Accounts' })).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Log in' })).toBeNull()
  })

  it('shows whether the API and database are up', async () => {
    mockApi(HEALTH)
    renderApp('/login', { token: null })
    expect(await screen.findByText(/API:/)).toHaveTextContent('API: up')
    expect(screen.getByText(/Database:/)).toHaveTextContent('Database: up')
  })

  it('shows the database as down when its check fails', async () => {
    mockApi({ 'GET /health': { status: 'ok' }, 'GET /health/db': { status: 503, body: {} } })
    renderApp('/login', { token: null })
    await screen.findByText(/API:/)
    expect(screen.getByText(/Database:/)).toHaveTextContent('Database: down')
  })
})

describe('accounts', () => {
  it('lists the accounts with their facts', async () => {
    loggedInApi()
    renderApp('/')
    const link = await screen.findByRole('link', { name: 'Demo account' })
    expect(link).toHaveAttribute('href', '/accounts/1')
    const card = link.closest('li')!
    expect(within(card).getByText('Example Broker · Demo · ZAR')).toBeInTheDocument()
    expect(within(card).getByText('9')).toBeInTheDocument()
    expect(within(card).getByText('10,000.00 ZAR')).toBeInTheDocument()
    expect(within(card).getByText('12 Mar 2026')).toBeInTheDocument()
  })

  it('invites you to create the first account', async () => {
    loggedInApi({ 'GET /accounts': [] })
    renderApp('/')
    expect(await screen.findByText('No accounts yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create your first account' })).toBeInTheDocument()
  })

  it('shows an error if the accounts cannot be loaded', async () => {
    loggedInApi({ 'GET /accounts': { status: 500, body: { detail: 'database is down' } } })
    renderApp('/')
    expect(await screen.findByRole('alert')).toHaveTextContent('database is down')
  })

  it('creates an account and opens it', async () => {
    const created = { ...ACCOUNT, id: 7, label: 'My IFX', trade_count: 0, last_close_time: null }
    const { calls } = loggedInApi({
      'POST /accounts': { status: 201, body: created },
      'GET /accounts/7': created,
    })
    renderApp('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'New account' }))

    await user.type(screen.getByLabelText('Name'), '  My IFX ')
    await user.clear(screen.getByLabelText('Currency'))
    await user.type(screen.getByLabelText('Currency'), 'zar')
    await user.clear(screen.getByLabelText('Starting balance'))
    await user.type(screen.getByLabelText('Starting balance'), '5000.50')
    await user.type(screen.getByLabelText(/Broker server time/), 'ny_close')
    await user.click(screen.getByLabelText('Demo account'))
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('heading', { name: 'My IFX' })).toBeInTheDocument()
    expect(screen.getByText('No trades yet')).toBeInTheDocument()
    const post = calls.find((c) => c.method === 'POST' && c.path === '/accounts')!
    expect(JSON.parse(post.body!)).toEqual({
      label: 'My IFX',
      broker: null,
      currency: 'ZAR',
      starting_balance: '5000.50',
      is_demo: true,
      server_timezone: 'ny_close',
    })
    expect(post.headers.Authorization).toBe('Bearer test-token')
  })

  it('shows what the API objects to, and keeps what was typed', async () => {
    loggedInApi({
      'POST /accounts': {
        status: 409,
        body: { detail: "you already have an account called 'Demo account'" },
      },
    })
    renderApp('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'New account' }))
    await user.type(screen.getByLabelText('Name'), 'Demo account')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('you already have an account')
    expect(screen.getByLabelText('Name')).toHaveValue('Demo account')
  })

  it('can cancel creating an account', async () => {
    loggedInApi()
    renderApp('/')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'New account' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('form', { name: 'New account' })).toBeNull()
  })
})

describe('account overview', () => {
  it('shows the headline, the key figures and both charts', async () => {
    loggedInApi()
    renderApp('/accounts/1')

    const hero = await screen.findByRole('region', { name: 'Net profit' })
    expect(hero).toHaveTextContent('-848.62')
    expect(hero).toHaveTextContent('ZAR')
    expect(hero).toHaveTextContent('9 trades, closed 4 Mar 2026 to 12 Mar 2026')

    const tile = (label: string) => screen.getByText(label).closest('.tile') as HTMLElement
    expect(tile('Return')).toHaveTextContent('-8.5%')
    expect(tile('Win rate')).toHaveTextContent('55.6%')
    expect(tile('Win rate')).toHaveTextContent('5 wins · 3 losses · 1 even')
    expect(tile('Profit factor')).toHaveTextContent('0.35')
    expect(tile('Expectancy')).toHaveTextContent('-94.29 ZAR')
    expect(tile('Average win')).toHaveTextContent('+91.38 ZAR')
    expect(tile('Average loss')).toHaveTextContent('-326.38 ZAR')
    expect(tile('Max drawdown')).toHaveTextContent('11.6%')
    expect(tile('Max drawdown')).toHaveTextContent('1,160.32 ZAR · not recovered')
    expect(tile('Average holding time')).toHaveTextContent('2h 30m')

    expect(screen.getAllByTestId('chart-line')).toHaveLength(2)
    expect(screen.getByRole('heading', { name: 'Account balance (ZAR)' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Drawdown from the highest balance' })).toBeInTheDocument()
  })

  it('draws drawdown downwards from the zero line', async () => {
    loggedInApi()
    renderApp('/accounts/1')
    await screen.findByRole('region', { name: 'Net profit' })
    const d = screen.getAllByTestId('chart-line')[1].getAttribute('d') ?? ''
    const ys = [...d.matchAll(/[ML]-?\d+\.\d (-?\d+\.\d)/g)].map((m) => Number(m[1]))
    expect(ys).toHaveLength(9)
    expect(ys[ys.length - 1]).toBeGreaterThan(ys[0]) // the last trade is the deepest drawdown
  })

  it('colors good and bad results and never relies on color alone', async () => {
    loggedInApi()
    renderApp('/accounts/1')
    const value = (await screen.findByRole('region', { name: 'Net profit' })).querySelector('.hero-value')!
    expect(value).toHaveClass('tone-bad')
    expect(value.textContent).toMatch(/^-848\.62/) // the minus sign is written out
  })

  it('asks for a period and keeps the figures while it loads', async () => {
    const { calls } = loggedInApi()
    renderApp('/accounts/1')
    const user = userEvent.setup()
    await screen.findByRole('region', { name: 'Net profit' })
    expect(calls.find((c) => c.path === '/accounts/1/summary')!.search).toBe('')

    await user.click(screen.getByRole('radio', { name: 'Last 90 days' }))
    await waitFor(() =>
      expect(calls.filter((c) => c.path === '/accounts/1/summary' && c.search.startsWith('?closed_from='))).toHaveLength(1),
    )
    const period = calls.find((c) => c.search.startsWith('?closed_from='))!
    expect(new URLSearchParams(period.search).get('closed_from')).toMatch(/^\d{4}-\d{2}-\d{2}T00:00:00\.000Z$/)
    // Both the summary and the curve are scoped to the same period.
    expect(calls.filter((c) => c.path === '/accounts/1/equity-curve' && c.search === period.search)).toHaveLength(1)
    expect(screen.getByRole('radio', { name: 'Last 90 days' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: 'All time' })).toHaveAttribute('aria-checked', 'false')
  })

  it('says when nothing closed in the chosen period', async () => {
    const empty = { ...SUMMARY, stats: { ...SUMMARY.stats, trades: 0 }, max_drawdown: null }
    loggedInApi({
      'GET /accounts/1/summary': (call: { search: string }) =>
        call.search ? { body: empty } : { body: SUMMARY },
      'GET /accounts/1/equity-curve': (call: { search: string }) =>
        call.search ? { body: { ...curve(), points: [] } } : { body: curve() },
    })
    renderApp('/accounts/1')
    const user = userEvent.setup()
    await screen.findByRole('region', { name: 'Net profit' })
    await user.click(screen.getByRole('radio', { name: 'Last 30 days' }))
    expect(await screen.findByText('No trades closed in this period')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Net profit' })).toBeNull()
  })

  it('invites you to bring trades in when the account is empty', async () => {
    loggedInApi({ 'GET /accounts/1': { ...ACCOUNT, trade_count: 0, last_close_time: null } })
    renderApp('/accounts/1')
    expect(await screen.findByText('No trades yet')).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: 'All time' })).toBeNull()
  })

  it('shows an error with a way to try again when the figures fail to load', async () => {
    let fail = true
    loggedInApi({
      'GET /accounts/1/summary': () =>
        fail ? { status: 500, body: { detail: 'something broke' } } : { body: SUMMARY },
    })
    renderApp('/accounts/1')
    const user = userEvent.setup()
    expect(await screen.findByRole('alert')).toHaveTextContent('something broke')
    fail = false
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('region', { name: 'Net profit' })).toBeInTheDocument()
  })

  it("says so when the account does not exist (or is somebody else's)", async () => {
    loggedInApi({ 'GET /accounts/9': { status: 404, body: { detail: 'account not found' } } })
    renderApp('/accounts/9')
    expect(await screen.findByRole('alert')).toHaveTextContent('That account does not exist.')
    expect(screen.getByRole('link', { name: '← Accounts' })).toHaveAttribute('href', '/')
  })

  it('has a table view for the balance chart', async () => {
    loggedInApi()
    renderApp('/accounts/1')
    await screen.findByRole('region', { name: 'Net profit' })
    const [balanceToggle] = screen.getAllByRole('button', { name: 'Show table' })
    fireEvent.click(balanceToggle)
    const rows = screen.getAllByRole('row')
    expect(rows).toHaveLength(10) // header + 9 trades
    expect(within(rows[1]).getByText('9,130.00 ZAR')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Trade #108')).toBeInTheDocument()
  })
})
