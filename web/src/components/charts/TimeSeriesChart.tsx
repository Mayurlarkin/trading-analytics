import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { formatDateTime } from '../../lib/format'
import { niceTicks, nearestIndex, timeTicks } from './scales'

export interface SeriesPoint {
  /** Milliseconds since the epoch. Points must be in ascending time order. */
  time: number
  value: number
  /** Extra line in the tooltip and table, e.g. which trade this is. */
  detail?: string
}

interface Props {
  title: string
  /** What the value is called in the tooltip and table header ("Balance", "Drawdown"). */
  valueLabel: string
  points: SeriesPoint[]
  /** A CSS color, normally a theme variable such as `var(--series-1)`. */
  color: string
  height?: number
  formatValue: (value: number) => string
  formatTick: (value: number) => string
  /** A hairline across the plot, e.g. the starting balance. */
  reference?: { value: number; label: string }
  /** Draw from zero at the top downwards (drawdown): the values are zero or negative. */
  hangingFromZero?: boolean
}

const MARGIN = { top: 12, right: 76, bottom: 26, left: 56 }
const FALLBACK_WIDTH = 720
const TABLE_ROWS = 200

function useWidth(ref: React.RefObject<HTMLDivElement | null>): number {
  const [width, setWidth] = useState(FALLBACK_WIDTH)
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.floor(entry.contentRect.width)
      if (next > 0) setWidth(next)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
  return width
}

/**
 * One series over time: a 2px line with a faint wash beneath, hairline grid, an end label,
 * a crosshair tooltip (mouse, touch and arrow keys) and a table view of the same numbers.
 */
export function TimeSeriesChart({
  title,
  valueLabel,
  points,
  color,
  height = 260,
  formatValue,
  formatTick,
  reference,
  hangingFromZero = false,
}: Props) {
  const frame = useRef<HTMLDivElement>(null)
  const svg = useRef<SVGSVGElement>(null)
  const width = useWidth(frame)
  const headingId = useId()
  const [active, setActive] = useState<number | null>(null)
  const [showTable, setShowTable] = useState(false)

  const plotWidth = Math.max(width - MARGIN.left - MARGIN.right, 10)
  const plotHeight = height - MARGIN.top - MARGIN.bottom

  const layout = useMemo(() => {
    if (points.length === 0) return null
    const times = points.map((p) => p.time)
    let t0 = times[0]
    let t1 = times[times.length - 1]
    if (t0 === t1) {
      t0 -= 12 * 3600 * 1000
      t1 += 12 * 3600 * 1000
    }

    const values = points.map((p) => p.value)
    if (reference) values.push(reference.value)
    let low = Math.min(...values)
    let high = Math.max(...values)
    if (hangingFromZero) high = 0
    const yTicks = niceTicks(low, high, 5)
    low = yTicks[0]
    high = yTicks[yTicks.length - 1]

    const x = (t: number) => MARGIN.left + ((t - t0) / (t1 - t0)) * plotWidth
    const y = (v: number) => MARGIN.top + (1 - (v - low) / (high - low)) * plotHeight
    return { times, t0, t1, yTicks, x, y, low, high, xTicks: timeTicks(t0, t1, Math.max(2, Math.floor(plotWidth / 90))) }
  }, [points, reference, hangingFromZero, plotWidth, plotHeight])

  if (layout === null) return null

  const { times, x, y, yTicks, xTicks, t0, t1 } = layout
  const linePath = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.time).toFixed(1)} ${y(p.value).toFixed(1)}`)
    .join(' ')
  const baseY = hangingFromZero ? y(0) : MARGIN.top + plotHeight
  const areaPath = `${linePath} L${x(points[points.length - 1].time).toFixed(1)} ${baseY.toFixed(1)} L${x(points[0].time).toFixed(1)} ${baseY.toFixed(1)} Z`

  const last = points[points.length - 1]
  const current = active === null ? null : points[active]

  function pick(event: PointerEvent<SVGRectElement>) {
    const box = svg.current?.getBoundingClientRect()
    // Convert the pointer position into the SVG's own units (it scales with the page).
    const scale = box && box.width > 0 ? width / box.width : 1
    const px = (event.clientX - (box?.left ?? 0)) * scale
    const t = t0 + ((px - MARGIN.left) / plotWidth) * (t1 - t0)
    setActive(nearestIndex(times, t))
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const lastIndex = points.length - 1
    const move: Record<string, (i: number | null) => number> = {
      ArrowRight: (i) => Math.min((i ?? -1) + 1, lastIndex),
      ArrowLeft: (i) => Math.max((i ?? lastIndex + 1) - 1, 0),
      Home: () => 0,
      End: () => lastIndex,
    }
    const next = move[event.key]
    if (next) {
      event.preventDefault()
      setActive(next(active))
    } else if (event.key === 'Escape') {
      setActive(null)
    }
  }

  const tooltipOnLeft = current !== null && x(current.time) > width * 0.6
  const tableRows = points.slice(-TABLE_ROWS).reverse()

  return (
    <figure className="chart" aria-labelledby={headingId}>
      <figcaption className="chart-head">
        <h3 id={headingId}>{title}</h3>
        <button type="button" className="link-button" onClick={() => setShowTable((v) => !v)}>
          {showTable ? 'Show chart' : 'Show table'}
        </button>
      </figcaption>

      {showTable ? (
        <div className="table-wrap" style={{ maxHeight: height }}>
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col" className="num">
                  {valueLabel}
                </th>
                <th scope="col">Trade</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((p) => (
                <tr key={p.time + (p.detail ?? '')}>
                  <td>{formatDateTime(p.time)}</td>
                  <td className="num">{formatValue(p.value)}</td>
                  <td>{p.detail ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {points.length > TABLE_ROWS && (
            <p className="muted small">Showing the latest {TABLE_ROWS} of {points.length} points.</p>
          )}
        </div>
      ) : (
        <div
          ref={frame}
          className="chart-frame"
          tabIndex={0}
          role="group"
          aria-label={`${title}. Use the left and right arrow keys to read values.`}
          onKeyDown={onKeyDown}
          onBlur={() => setActive(null)}
        >
          <svg
            ref={svg}
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={`${title}: ${points.length} points, ending at ${formatValue(last.value)}`}
          >
            {yTicks.map((tick) => (
              <g key={tick}>
                <line className="grid" x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(tick)} y2={y(tick)} />
                <text className="tick" x={MARGIN.left - 8} y={y(tick)} textAnchor="end" dominantBaseline="middle">
                  {formatTick(tick)}
                </text>
              </g>
            ))}
            {xTicks.map((tick) => (
              <text
                key={tick.value}
                className="tick"
                x={x(tick.value)}
                y={height - 6}
                textAnchor="middle"
              >
                {tick.label}
              </text>
            ))}
            {hangingFromZero && (
              <line className="axis" x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(0)} y2={y(0)} />
            )}
            {reference && (
              <g>
                <line
                  className="reference"
                  x1={MARGIN.left}
                  x2={MARGIN.left + plotWidth}
                  y1={y(reference.value)}
                  y2={y(reference.value)}
                />
                <text
                  className="tick"
                  x={MARGIN.left + plotWidth + 8}
                  y={y(reference.value)}
                  dominantBaseline="middle"
                >
                  {reference.label}
                </text>
              </g>
            )}

            <path data-testid="chart-area" d={areaPath} fill={color} fillOpacity={0.1} />
            <path
              data-testid="chart-line"
              d={linePath}
              fill="none"
              stroke={color}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />

            {active === null && (
              <g>
                <circle className="dot-ring" cx={x(last.time)} cy={y(last.value)} r={6} />
                <circle cx={x(last.time)} cy={y(last.value)} r={4} fill={color} />
                <text
                  className="end-label"
                  x={x(last.time) + 10}
                  y={y(last.value)}
                  dominantBaseline="middle"
                >
                  {formatTick(last.value)}
                </text>
              </g>
            )}

            {current && (
              <g pointerEvents="none">
                <line
                  className="crosshair"
                  x1={x(current.time)}
                  x2={x(current.time)}
                  y1={MARGIN.top}
                  y2={MARGIN.top + plotHeight}
                />
                <circle className="dot-ring" cx={x(current.time)} cy={y(current.value)} r={6} />
                <circle cx={x(current.time)} cy={y(current.value)} r={4} fill={color} />
              </g>
            )}

            <rect
              data-testid="chart-hit"
              x={MARGIN.left}
              y={MARGIN.top}
              width={plotWidth}
              height={plotHeight}
              fill="transparent"
              onPointerMove={pick}
              onPointerDown={pick}
              onPointerLeave={() => setActive(null)}
            />
          </svg>

          {current && (
            <div
              className="tooltip"
              role="status"
              style={{
                top: MARGIN.top,
                [tooltipOnLeft ? 'right' : 'left']: tooltipOnLeft
                  ? width - x(current.time) + 12
                  : x(current.time) + 12,
              }}
            >
              <div className="tooltip-time">{formatDateTime(current.time)}</div>
              <div className="tooltip-row">
                <span className="key" style={{ background: color }} aria-hidden="true" />
                <strong>{formatValue(current.value)}</strong>
                <span className="muted">{valueLabel}</span>
              </div>
              {current.detail && <div className="muted small">{current.detail}</div>}
            </div>
          )}
        </div>
      )}
    </figure>
  )
}
