import { PERIODS, type PeriodKey } from '../lib/period'

interface Props {
  value: PeriodKey
  onChange: (key: PeriodKey) => void
}

export function PeriodFilter({ value, onChange }: Props) {
  return (
    <div className="filters" role="radiogroup" aria-label="Period">
      {PERIODS.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          role="radio"
          aria-checked={value === key}
          className={`chip${value === key ? ' is-selected' : ''}`}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
