import { createContext } from 'react'
import type { RequestOptions } from '../api/http'

export interface AuthValue {
  /** The login token, or null when logged out. */
  token: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  /** An API call that sends the token, and logs out if the API says it is no longer valid. */
  request: <T>(path: string, options?: RequestOptions) => Promise<T>
}

export const AuthContext = createContext<AuthValue | null>(null)
