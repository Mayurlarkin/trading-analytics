export type PeriodKey = 'all' | '365' | '90' | '30'

export const PERIODS: { key: PeriodKey; label: string }[] = [
  { key: 'all', label: 'All time' },
  { key: '365', label: 'Last 12 months' },
  { key: '90', label: 'Last 90 days' },
  { key: '30', label: 'Last 30 days' },
]

const DAY_MS = 24 * 60 * 60 * 1000

/**
 * The query string that limits a request to a period ("" for all time).
 *
 * The start is the beginning of a UTC day, so the same request is repeated all day long
 * (and can be cached) instead of changing every millisecond.
 */
export function periodQuery(key: PeriodKey, now: Date = new Date()): string {
  if (key === 'all') return ''
  const startOfToday = Math.floor(now.getTime() / DAY_MS) * DAY_MS
  const from = new Date(startOfToday - Number(key) * DAY_MS)
  return `?closed_from=${encodeURIComponent(from.toISOString())}`
}
