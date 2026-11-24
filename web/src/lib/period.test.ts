import { describe, expect, it } from 'vitest'
import { periodQuery } from './period'

describe('periodQuery', () => {
  it('asks for everything when the period is all time', () => {
    expect(periodQuery('all')).toBe('')
  })

  it('starts at the beginning of a UTC day, so repeated requests are identical', () => {
    const morning = new Date('2026-06-15T01:02:03Z')
    const evening = new Date('2026-06-15T23:59:59Z')
    expect(periodQuery('30', morning)).toBe(periodQuery('30', evening))
    expect(decodeURIComponent(periodQuery('30', morning))).toBe('?closed_from=2026-05-16T00:00:00.000Z')
  })

  it('counts back the right number of days', () => {
    const now = new Date('2026-06-15T12:00:00Z')
    expect(decodeURIComponent(periodQuery('90', now))).toBe('?closed_from=2026-03-17T00:00:00.000Z')
    expect(decodeURIComponent(periodQuery('365', now))).toBe('?closed_from=2025-06-15T00:00:00.000Z')
  })
})
