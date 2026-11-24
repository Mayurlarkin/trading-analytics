import { describe, expect, it } from 'vitest'
import {
  formatDate,
  formatDateTime,
  formatDuration,
  formatMoney,
  formatPercent,
  formatRatio,
  formatSignedMoney,
  formatSignedPercent,
  formatTick,
  toNumber,
} from './format'

describe('format', () => {
  it('shows money with thousands separators and two decimals', () => {
    expect(formatMoney('1234567.5')).toBe('1,234,567.50')
    expect(formatMoney('-0.5')).toBe('-0.50')
    expect(formatMoney(null)).toBe('—')
    expect(formatMoney('not a number')).toBe('—')
  })

  it('writes the sign of a signed amount out in full', () => {
    expect(formatSignedMoney('12.3')).toBe('+12.30')
    expect(formatSignedMoney('-12.3')).toBe('-12.30')
    expect(formatSignedMoney('0')).toBe('0.00')
    expect(formatSignedMoney(undefined)).toBe('—')
  })

  it('turns fractions into percentages', () => {
    expect(formatPercent('0.5637')).toBe('56.4%')
    expect(formatPercent('0.84694', 2)).toBe('84.69%')
    expect(formatSignedPercent('0.05')).toBe('+5.0%')
    expect(formatSignedPercent('-0.05')).toBe('-5.0%')
    expect(formatPercent(null)).toBe('—')
  })

  it('formats ratios, ticks, dates and durations', () => {
    expect(formatRatio('0.62414')).toBe('0.62')
    expect(formatTick(1234.4)).toBe('1,234')
    expect(formatTick(20_000)).toBe('20K')
    expect(formatTick(-25_000)).toBe('-25K')
    expect(formatDate('2026-03-03T23:30:00Z')).toBe('3 Mar 2026')
    expect(formatDate(null)).toBe('—')
    expect(formatDateTime('2026-03-03T09:05:00Z')).toBe('3 Mar 2026, 09:05 UTC')
    expect(formatDuration(45)).toBe('45s')
    expect(formatDuration(9001)).toBe('2h 30m')
    expect(formatDuration(3 * 86400 + 7200)).toBe('3d 2h')
    expect(formatDuration(null)).toBe('—')
  })

  it('converts only real numbers', () => {
    expect(toNumber('1.5')).toBe(1.5)
    expect(toNumber('')).toBeNull()
    expect(toNumber('abc')).toBeNull()
  })
})
