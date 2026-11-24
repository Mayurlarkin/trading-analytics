import { describe, expect, it, vi } from 'vitest'
import { ApiError, errorMessage, request } from './http'

describe('errorMessage', () => {
  it('uses a plain string as it is', () => {
    expect(errorMessage('incorrect email or password')).toBe('incorrect email or password')
  })

  it('lists validation problems with the field they belong to', () => {
    const detail = [
      { loc: ['body', 'currency'], msg: 'String should match pattern' },
      { loc: ['body', 'starting_balance'], msg: 'Input should be greater than or equal to 0' },
    ]
    expect(errorMessage(detail)).toBe(
      'currency: String should match pattern; starting_balance: Input should be greater than or equal to 0',
    )
  })

  it('reads the message of an object and falls back to something readable', () => {
    expect(errorMessage({ message: 'the report has invalid rows' })).toBe('the report has invalid rows')
    expect(errorMessage(null)).toMatch(/something went wrong/i)
    expect(errorMessage([])).toMatch(/something went wrong/i)
  })
})

describe('request', () => {
  it('sends the token and parses JSON', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: 1 }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(request('/x', { token: 'abc' })).resolves.toEqual({ ok: 1 })
    const init = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect((init[1].headers as Record<string, string>).Authorization).toBe('Bearer abc')
  })

  it('does not send an Authorization header without a token', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await request('/x')
    const init = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(init[1].headers).not.toHaveProperty('Authorization')
  })

  it('sends JSON and form bodies with the right content type', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await request('/a', { method: 'POST', json: { a: 1 } })
    await request('/b', { method: 'POST', form: { username: 'a@b.c', password: 'p w' } })
    const [, jsonInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    const [, formInit] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect((jsonInit.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(jsonInit.body).toBe('{"a":1}')
    expect(String(formInit.body)).toBe('username=a%40b.c&password=p+w')
  })

  it('turns an error answer into an ApiError with the API message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ detail: 'account not found' }), { status: 404 })),
    )
    const error = await request('/x').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, message: 'account not found' })
  })

  it('copes with an error answer that is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>Bad gateway</html>', { status: 502 })))
    await expect(request('/x')).rejects.toMatchObject({ status: 502 })
  })

  it('reports an unreachable API as status 0', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))))
    await expect(request('/x')).rejects.toMatchObject({ status: 0, message: expect.stringMatching(/cannot reach/i) })
  })

  it('returns nothing for 204', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })))
    await expect(request('/x', { method: 'DELETE' })).resolves.toBeUndefined()
  })
})
