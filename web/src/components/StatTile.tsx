import type { ReactNode } from 'react'

interface Props {
  label: string
  value: ReactNode
  /** A line of context under the value. */
  sub?: ReactNode
  /** Colors the value as good or bad (the +/- sign is always written out too, so color never carries the meaning alone). */
  tone?: 'good' | 'bad'
}

export function StatTile({ label, value, sub, tone }: Props) {
  return (
    <div className="tile">
      <dt className="tile-label">{label}</dt>
      <dd className={`tile-value${tone ? ` tone-${tone}` : ''}`}>{value}</dd>
      {sub !== undefined && <dd className="tile-sub">{sub}</dd>}
    </div>
  )
}
