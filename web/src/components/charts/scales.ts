/** Round-number axis values that cover [min, max], about `count` of them. */
export function niceTicks(min: number, max: number, count = 5): number[] {
  if (min === max) {
    const pad = Math.abs(min) || 1
    min -= pad
    max += pad
  }
  const rawStep = (max - min) / Math.max(count - 1, 1)
  const magnitude = 10 ** Math.floor(Math.log10(rawStep))
  const normalised = rawStep / magnitude
  const nice = [1, 2, 2.5, 5, 10].find((n) => normalised <= n) ?? 10
  const step = nice * magnitude
  const first = Math.floor(min / step)
  const last = Math.ceil(max / step)
  const ticks: number[] = []
  for (let i = first; i <= last; i++) ticks.push(Number((i * step).toPrecision(12)))
  return ticks
}

export interface TimeTick {
  value: number
  label: string
}

const DAY_MS = 24 * 60 * 60 * 1000
const MONTH_LABEL = new Intl.DateTimeFormat('en-GB', {
  month: 'short',
  year: '2-digit',
  timeZone: 'UTC',
})
const DAY_LABEL = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  timeZone: 'UTC',
})

/** Axis ticks on month starts (long spans) or on UTC midnights (short ones), at most `max`. */
export function timeTicks(min: number, max: number, maxTicks = 6): TimeTick[] {
  const spanDays = (max - min) / DAY_MS
  const ticks: TimeTick[] = []

  if (spanDays > 75) {
    const start = new Date(min)
    const months = Math.max(1, Math.round(spanDays / 30))
    const every = [1, 2, 3, 6, 12, 24, 60].find((m) => months / m <= maxTicks) ?? 60
    let year = start.getUTCFullYear()
    let month = start.getUTCMonth() + 1 // the first month start after the data begins
    for (;;) {
      const value = Date.UTC(year, month, 1)
      if (value > max) break
      if (month % every === 0 || every === 1) {
        ticks.push({ value, label: MONTH_LABEL.format(value) })
      }
      month += 1
      if (month > 11) {
        month = 0
        year += 1
      }
    }
    return ticks
  }

  const every = [1, 2, 3, 7, 14, 30].find((d) => Math.ceil(spanDays) / d <= maxTicks) ?? 30
  const firstDay = Math.ceil(min / DAY_MS)
  for (let day = firstDay; day * DAY_MS <= max; day++) {
    if (day % every === 0) ticks.push({ value: day * DAY_MS, label: DAY_LABEL.format(day * DAY_MS) })
  }
  return ticks
}

/** Index of the time closest to `t` in an ascending list (-1 for an empty list). */
export function nearestIndex(times: number[], t: number): number {
  if (times.length === 0) return -1
  let low = 0
  let high = times.length - 1
  while (low < high) {
    const mid = (low + high) >> 1
    if (times[mid] < t) low = mid + 1
    else high = mid
  }
  if (low > 0 && t - times[low - 1] <= times[low] - t) return low - 1
  return low
}
