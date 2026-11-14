import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

function mockFetch(handler: (url: string) => Promise<{ ok: boolean }>) {
  vi.stubGlobal('fetch', vi.fn((url: string) => handler(url)))
}

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows API and database as up when both health checks pass', async () => {
    mockFetch(() => Promise.resolve({ ok: true }))
    render(<App />)

    expect(screen.getByText('Checking…')).toBeInTheDocument()
    expect(await screen.findByText(/API:/)).toHaveTextContent('API: up')
    expect(screen.getByText(/Database:/)).toHaveTextContent('Database: up')
  })

  it('shows the database as down when only the database check fails', async () => {
    mockFetch((url) => Promise.resolve({ ok: !url.endsWith('/health/db') }))
    render(<App />)

    expect(await screen.findByText(/API:/)).toHaveTextContent('API: up')
    expect(screen.getByText(/Database:/)).toHaveTextContent('Database: down')
  })

  it('shows both as down when the API is unreachable', async () => {
    mockFetch(() => Promise.reject(new Error('network down')))
    render(<App />)

    expect(await screen.findByText(/API:/)).toHaveTextContent('API: down')
    expect(screen.getByText(/Database:/)).toHaveTextContent('Database: down')
  })
})
