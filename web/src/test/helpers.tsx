import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import App from '../App'
import { AuthProvider } from '../auth/AuthProvider'

export interface Call {
  method: string
  path: string
  search: string
  headers: Record<string, string>
  body: string | null
}

type Handler = (call: Call) => { status?: number; body?: unknown } | Promise<{ status?: number; body?: unknown }>

type Reply = { status?: number; body?: unknown }

/** A route is either a reply ({ status?, body? }) or just the JSON to answer with. */
function toReply(route: unknown): Reply {
  if (route && typeof route === 'object' && !Array.isArray(route)) {
    const keys = Object.keys(route)
    const looksLikeReply =
      keys.every((k) => k === 'status' || k === 'body') &&
      ('body' in route || typeof (route as Reply).status === 'number')
    if (looksLikeReply) return route as Reply
  }
  return { body: route }
}

/**
 * Replace fetch with a fake API. Keys look like "GET /accounts" (the path without the query
 * string). Anything not listed answers 404, so a forgotten request fails loudly.
 */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const calls: Call[] = []
  const fetchMock = vi.fn(async (url: string | URL, init?: RequestInit) => {
    const parsed = new URL(String(url))
    const method = init?.method ?? 'GET'
    const call: Call = {
      method,
      path: parsed.pathname,
      search: parsed.search,
      headers: Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>)),
      body: init?.body ? String(init.body) : null,
    }
    calls.push(call)
    const route = routes[`${method} ${parsed.pathname}`]
    if (route === undefined) {
      return new Response(JSON.stringify({ detail: 'not found' }), { status: 404 })
    }
    const result = typeof route === 'function' ? await (route as Handler)(call) : toReply(route)
    return new Response(JSON.stringify(result.body ?? null), { status: result.status ?? 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}

export const HEALTH = { 'GET /health': { status: 'ok' }, 'GET /health/db': { status: 'ok' } }

export function renderApp(route = '/', { token = 'test-token' as string | null } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider initialToken={token}>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
