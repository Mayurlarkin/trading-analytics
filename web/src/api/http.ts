export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/** An error answer from the API (or status 0 when it could not be reached at all). */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Turn the API's `detail` (a string, a list of validation problems, or an object) into text. */
export function errorMessage(detail: unknown): string {
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (item && typeof item === 'object' && 'msg' in item) {
        const { loc, msg } = item as { loc?: unknown[]; msg: unknown }
        const field = (loc ?? []).filter((p) => p !== 'body' && p !== 'query').join('.')
        return field ? `${field}: ${String(msg)}` : String(msg)
      }
      return String(item)
    })
    if (parts.length) return parts.join('; ')
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  return 'Something went wrong. Please try again.'
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  token?: string | null
  json?: unknown
  form?: Record<string, string>
  signal?: AbortSignal
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.token) headers.Authorization = `Bearer ${options.token}`

  let body: BodyInit | undefined
  if (options.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.json)
  } else if (options.form) {
    body = new URLSearchParams(options.form)
  }

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body,
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'Cannot reach the API. Check that it is running.')
  }

  if (response.status === 204) return undefined as T

  let data: unknown = null
  try {
    data = await response.json()
  } catch {
    // an empty or non-JSON body: fall through to the status-based message below
  }

  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : null
    throw new ApiError(response.status, errorMessage(detail))
  }
  return data as T
}
