import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { ApiError, request as send, type RequestOptions } from '../api/http'
import type { TokenResponse } from '../api/types'
import { AuthContext, type AuthValue } from './context'

const STORAGE_KEY = 'ta.token'

// The token lives in sessionStorage: it survives a page reload but not closing the tab, and
// is not shared between tabs. (A cookie the page cannot read would be safer against script
// injection; that belongs with the deployment hardening.) Storage can be unavailable or full,
// so every access is guarded and the app still works for the current page view.
function readStoredToken(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function storeToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(STORAGE_KEY, token)
    else sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore: see above
  }
}

export function AuthProvider({
  children,
  initialToken,
}: {
  children: ReactNode
  /** For tests: start logged in (or out, with null) without touching storage. */
  initialToken?: string | null
}) {
  const queryClient = useQueryClient()
  const [token, setToken] = useState<string | null>(
    initialToken === undefined ? readStoredToken() : initialToken,
  )

  const logout = useCallback(() => {
    storeToken(null)
    setToken(null)
    queryClient.clear() // nothing of the previous person may stay in memory
  }, [queryClient])

  const login = useCallback(async (email: string, password: string) => {
    // The API's login form is the standard OAuth2 one: the email goes in "username".
    const response = await send<TokenResponse>('/auth/login', {
      method: 'POST',
      form: { username: email, password },
    })
    storeToken(response.access_token)
    setToken(response.access_token)
  }, [])

  const request = useCallback(
    async <T,>(path: string, options: RequestOptions = {}): Promise<T> => {
      try {
        return await send<T>(path, { ...options, token })
      } catch (error) {
        if (error instanceof ApiError && error.status === 401 && token) logout()
        throw error
      }
    },
    [token, logout],
  )

  const value = useMemo<AuthValue>(
    () => ({ token, login, logout, request }),
    [token, login, logout, request],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
