import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from './AuthProvider'
import type { AuthValue } from './context'
import { useAuth } from './useAuth'

function Capture({ onAuth }: { onAuth: (auth: AuthValue) => void }) {
  onAuth(useAuth())
  return null
}

describe('AuthProvider', () => {
  it('forgets everything that was loaded when someone logs out', () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(['accounts'], [{ id: 1, label: 'Private account' }])
    let auth!: AuthValue
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider initialToken="t">
          <Capture onAuth={(a) => (auth = a)} />
        </AuthProvider>
      </QueryClientProvider>,
    )
    expect(queryClient.getQueryData(['accounts'])).toBeDefined()
    act(() => auth.logout())
    expect(queryClient.getQueryData(['accounts'])).toBeUndefined()
    expect(auth.token).toBeNull()
  })

  it('refuses to be used outside the provider', () => {
    expect(() => render(<Capture onAuth={() => undefined} />)).toThrow(/AuthProvider/)
  })
})
