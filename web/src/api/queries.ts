import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/useAuth'
import { periodQuery, type PeriodKey } from '../lib/period'
import type { Account, AccountCreate, EquityCurve, Summary, User } from './types'

export function useMe() {
  const { request, token } = useAuth()
  return useQuery({
    queryKey: ['me'],
    queryFn: () => request<User>('/auth/me'),
    enabled: token !== null,
    staleTime: Infinity,
  })
}

export function useAccounts() {
  const { request, token } = useAuth()
  return useQuery({
    queryKey: ['accounts'],
    queryFn: () => request<Account[]>('/accounts'),
    enabled: token !== null,
  })
}

export function useAccount(id: number) {
  const { request, token } = useAuth()
  return useQuery({
    queryKey: ['accounts', id],
    queryFn: () => request<Account>(`/accounts/${id}`),
    enabled: token !== null && Number.isInteger(id),
  })
}

// While a new period loads, keep showing the previous figures (dimmed by the page)
// instead of blanking the screen.
export function useSummary(id: number, period: PeriodKey) {
  const { request, token } = useAuth()
  const query = periodQuery(period)
  return useQuery({
    queryKey: ['accounts', id, 'summary', query],
    queryFn: () => request<Summary>(`/accounts/${id}/summary${query}`),
    enabled: token !== null && Number.isInteger(id),
    placeholderData: keepPreviousData,
  })
}

export function useEquityCurve(id: number, period: PeriodKey) {
  const { request, token } = useAuth()
  const query = periodQuery(period)
  return useQuery({
    queryKey: ['accounts', id, 'equity-curve', query],
    queryFn: () => request<EquityCurve>(`/accounts/${id}/equity-curve${query}`),
    enabled: token !== null && Number.isInteger(id),
    placeholderData: keepPreviousData,
  })
}

export function useCreateAccount() {
  const { request } = useAuth()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: AccountCreate) =>
      request<Account>('/accounts', { method: 'POST', json: payload }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['accounts'] }),
  })
}
