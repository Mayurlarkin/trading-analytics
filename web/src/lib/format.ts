const NUMBER = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const WHOLE = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const COMPACT = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })
const DATE = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
})
const DATE_TIME = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'UTC',
})

export const NO_VALUE = '—'

/** The API sends decimals as strings; only convert to a number to show or to draw. */
export function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : null
}

/** "-1,234.50": thousands separated, two decimals, no currency (the code is shown beside it). */
export function formatMoney(value: string | number | null | undefined): string {
  const n = toNumber(value)
  return n === null ? NO_VALUE : NUMBER.format(n)
}

/** "+1,234.50" / "-1,234.50": the sign is always shown. */
export function formatSignedMoney(value: string | number | null | undefined): string {
  const n = toNumber(value)
  if (n === null) return NO_VALUE
  return `${n > 0 ? '+' : ''}${NUMBER.format(n)}`
}

/** Whole numbers for axis ticks, compact (20K) once they reach 10,000. */
export function formatTick(value: number): string {
  return Math.abs(value) >= 10_000 ? COMPACT.format(value) : WHOLE.format(value)
}

/** A fraction as a percentage: 0.5637 -> "56.4%". */
export function formatPercent(fraction: string | number | null | undefined, digits = 1): string {
  const n = toNumber(fraction)
  if (n === null) return NO_VALUE
  return `${(n * 100).toFixed(digits)}%`
}

/** "+5.3%" / "-5.3%": a fraction as a percentage, with the sign always shown. */
export function formatSignedPercent(fraction: string | number | null | undefined, digits = 1): string {
  const n = toNumber(fraction)
  if (n === null) return NO_VALUE
  return `${n > 0 ? '+' : ''}${(n * 100).toFixed(digits)}%`
}

export function formatRatio(value: string | number | null | undefined): string {
  const n = toNumber(value)
  return n === null ? NO_VALUE : n.toFixed(2)
}

export function formatDate(iso: string | number | null | undefined): string {
  if (iso === null || iso === undefined) return NO_VALUE
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? NO_VALUE : DATE.format(date)
}

export function formatDateTime(time: string | number): string {
  const date = new Date(time)
  return Number.isNaN(date.getTime()) ? NO_VALUE : `${DATE_TIME.format(date)} UTC`
}

/** 9001 -> "2h 30m"; under a minute -> "45s". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return NO_VALUE
  if (seconds < 60) return `${Math.round(seconds)}s`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours < 24) return rest ? `${hours}h ${rest}m` : `${hours}h`
  const days = Math.floor(hours / 24)
  return `${days}d ${hours % 24}h`
}
