import { describe, expect, it } from 'vitest'
import { nearestIndex, niceTicks, timeTicks } from './scales'

describe('niceTicks', () => {
  it('uses round numbers that cover the range', () => {
    expect(niceTicks(0, 100, 5)).toEqual([0, 25, 50, 75, 100])
    expect(niceTicks(9_340, 10_870, 5)).toEqual([9_000, 9_500, 10_000, 10_500, 11_000])
    expect(niceTicks(-37, 0, 5)).toEqual([-40, -30, -20, -10, 0])
  })

  it('handles a flat series without dividing by zero', () => {
    const ticks = niceTicks(500, 500, 5)
    expect(ticks[0]).toBeLessThan(500)
    expect(ticks[ticks.length - 1]).toBeGreaterThan(500)
    expect(niceTicks(0, 0, 5).length).toBeGreaterThan(1)
  })

  it('does not accumulate floating point noise', () => {
    expect(niceTicks(0, 1, 6)).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1])
  })
})

describe('timeTicks', () => {
  const utc = (y: number, m: number, d: number) => Date.UTC(y, m - 1, d)

  it('puts long spans on month starts, with a limited count', () => {
    const ticks = timeTicks(utc(2026, 3, 3), utc(2026, 11, 12))
    expect(ticks.length).toBeGreaterThan(1)
    expect(ticks.length).toBeLessThanOrEqual(6)
    for (const tick of ticks) expect(new Date(tick.value).getUTCDate()).toBe(1)
    expect(ticks[0].label).toMatch(/^\w{3} 26$/)
  })

  it('puts short spans on midnights', () => {
    const ticks = timeTicks(utc(2026, 3, 1) + 5 * 3600_000, utc(2026, 3, 9))
    expect(ticks.length).toBeGreaterThan(1)
    for (const tick of ticks) expect(tick.value % 86_400_000).toBe(0)
  })

  it('stays inside the range', () => {
    const min = utc(2026, 1, 20)
    const max = utc(2026, 8, 5)
    for (const tick of timeTicks(min, max)) {
      expect(tick.value).toBeGreaterThanOrEqual(min)
      expect(tick.value).toBeLessThanOrEqual(max)
    }
  })

  it('gives no ticks for a tiny span with no midnight inside', () => {
    expect(timeTicks(utc(2026, 3, 1) + 3600_000, utc(2026, 3, 1) + 7200_000)).toEqual([])
  })
})

describe('nearestIndex', () => {
  const times = [10, 20, 40, 80]

  it('finds the closest point either side', () => {
    expect(nearestIndex(times, 10)).toBe(0)
    expect(nearestIndex(times, 14)).toBe(0)
    expect(nearestIndex(times, 16)).toBe(1)
    expect(nearestIndex(times, 59)).toBe(2)
    expect(nearestIndex(times, 61)).toBe(3)
  })

  it('clamps outside the data and copes with nothing', () => {
    expect(nearestIndex(times, -100)).toBe(0)
    expect(nearestIndex(times, 1000)).toBe(3)
    expect(nearestIndex([], 5)).toBe(-1)
    expect(nearestIndex([7], 5)).toBe(0)
  })

  it('prefers the earlier point on an exact tie', () => {
    expect(nearestIndex(times, 30)).toBe(1)
  })
})
