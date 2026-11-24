import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TimeSeriesChart, type SeriesPoint } from './TimeSeriesChart'

const DAY = 86_400_000
const START = Date.UTC(2026, 2, 3)

function points(values: number[]): SeriesPoint[] {
  return values.map((value, i) => ({ time: START + i * DAY, value, detail: `Trade #${i + 1}` }))
}

function chart(values = [100, 150, 120, 200], extra: Partial<React.ComponentProps<typeof TimeSeriesChart>> = {}) {
  return render(
    <TimeSeriesChart
      title="Balance"
      valueLabel="Balance"
      color="var(--series-1)"
      points={points(values)}
      formatValue={(v) => `${v.toFixed(2)} USD`}
      formatTick={(v) => String(v)}
      {...extra}
    />,
  )
}

describe('TimeSeriesChart', () => {
  it('draws one line through every point', () => {
    chart()
    const d = screen.getByTestId('chart-line').getAttribute('d') ?? ''
    expect(d.startsWith('M')).toBe(true)
    expect(d.match(/L/g)).toHaveLength(3)
    expect(screen.getByTestId('chart-area').getAttribute('d')).toMatch(/Z$/)
  })

  it('goes up the page for higher values', () => {
    chart([100, 200])
    const coordinates = (screen.getByTestId('chart-line').getAttribute('d') ?? '').match(/-?\d+\.\d/g)!.map(Number)
    const [, firstY, , secondY] = coordinates
    expect(secondY).toBeLessThan(firstY) // SVG y grows downwards
  })

  it('draws nothing for an empty series, and copes with a single point', () => {
    const { container } = chart([])
    expect(container.querySelector('svg')).toBeNull()
    chart([42])
    expect(screen.getByTestId('chart-line').getAttribute('d')).toMatch(/^M/)
  })

  it('labels the end of the line and describes the chart for screen readers', () => {
    const { container } = chart()
    expect(screen.getByRole('img', { name: /Balance: 4 points, ending at 200.00 USD/ })).toBeInTheDocument()
    expect(container.querySelector('.end-label')).toHaveTextContent('200')
  })

  it('shows a reference line with its label', () => {
    chart([100, 150], { reference: { value: 100, label: 'Start' } })
    expect(screen.getByText('Start')).toBeInTheDocument()
  })

  it('reads values with the arrow keys and closes with Escape', () => {
    chart()
    const frame = screen.getByRole('group', { name: /arrow keys/i })
    frame.focus()
    expect(screen.queryByRole('status')).toBeNull()

    fireEvent.keyDown(frame, { key: 'ArrowRight' })
    expect(within(screen.getByRole('status')).getByText('100.00 USD')).toBeInTheDocument()
    fireEvent.keyDown(frame, { key: 'ArrowRight' })
    expect(within(screen.getByRole('status')).getByText('150.00 USD')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Trade #2')
    expect(screen.getByRole('status')).toHaveTextContent('4 Mar 2026')
    fireEvent.keyDown(frame, { key: 'ArrowLeft' })
    expect(screen.getByRole('status')).toHaveTextContent('100.00 USD')
    fireEvent.keyDown(frame, { key: 'End' })
    expect(screen.getByRole('status')).toHaveTextContent('200.00 USD')
    fireEvent.keyDown(frame, { key: 'Home' })
    expect(screen.getByRole('status')).toHaveTextContent('100.00 USD')
    fireEvent.keyDown(frame, { key: 'Escape' })
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('does not run past either end', () => {
    chart()
    const frame = screen.getByRole('group', { name: /arrow keys/i })
    fireEvent.keyDown(frame, { key: 'End' })
    fireEvent.keyDown(frame, { key: 'ArrowRight' })
    expect(screen.getByRole('status')).toHaveTextContent('200.00 USD')
    fireEvent.keyDown(frame, { key: 'Home' })
    fireEvent.keyDown(frame, { key: 'ArrowLeft' })
    expect(screen.getByRole('status')).toHaveTextContent('100.00 USD')
  })

  it('follows the pointer to the nearest point', () => {
    chart()
    const hit = screen.getByTestId('chart-hit')
    const x = Number(hit.getAttribute('x'))
    const width = Number(hit.getAttribute('width'))
    // jsdom has no layout, so the pointer position is already in SVG units.
    fireEvent.pointerMove(hit, { clientX: x + 1 })
    expect(screen.getByRole('status')).toHaveTextContent('100.00 USD')
    fireEvent.pointerMove(hit, { clientX: x + width - 1 })
    expect(screen.getByRole('status')).toHaveTextContent('200.00 USD')
    fireEvent.pointerMove(hit, { clientX: x + width / 3 })
    expect(screen.getByRole('status')).toHaveTextContent('150.00 USD')
    fireEvent.pointerLeave(hit)
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('shows text from the data as text, never as markup', () => {
    render(
      <TimeSeriesChart
        title="Balance"
        valueLabel="Balance"
        color="var(--series-1)"
        points={[{ time: START, value: 1, detail: '<img src=x onerror=alert(1)>' }]}
        formatValue={String}
        formatTick={String}
      />,
    )
    fireEvent.keyDown(screen.getByRole('group'), { key: 'Home' })
    expect(screen.getByRole('status')).toHaveTextContent('<img src=x onerror=alert(1)>')
    expect(document.querySelector('img')).toBeNull()
  })

  it('offers the same numbers as a table', () => {
    chart()
    fireEvent.click(screen.getByRole('button', { name: 'Show table' }))
    const rows = screen.getAllByRole('row')
    expect(rows).toHaveLength(5) // header + 4 points
    expect(within(rows[1]).getByText('200.00 USD')).toBeInTheDocument() // newest first
    expect(within(rows[1]).getByText('Trade #4')).toBeInTheDocument()
    expect(screen.queryByTestId('chart-line')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Show chart' }))
    expect(screen.getByTestId('chart-line')).toBeInTheDocument()
  })

  it('keeps a long table to the latest rows and says so', () => {
    chart(Array.from({ length: 250 }, (_, i) => i))
    fireEvent.click(screen.getByRole('button', { name: 'Show table' }))
    expect(screen.getAllByRole('row')).toHaveLength(201)
    expect(screen.getByText(/latest 200 of 250/)).toBeInTheDocument()
  })

  it('hangs from zero for drawdown charts: the zero line is at the top', () => {
    chart([0, -5, -20, -10], { hangingFromZero: true })
    const d = screen.getByTestId('chart-line').getAttribute('d') ?? ''
    const ys = d.match(/ (\d+\.\d)/g)!.map((s) => Number(s))
    expect(ys[0]).toBeLessThan(ys[2]) // 0 is higher on the page than -20
    // The wash is filled back to the zero line, not to the bottom of the plot.
    const area = screen.getByTestId('chart-area').getAttribute('d') ?? ''
    const closing = [...area.matchAll(/L-?\d+\.\d (-?\d+\.\d)/g)].map((m) => Number(m[1]))
    expect(closing.slice(-2)).toEqual([ys[0], ys[0]])
  })
})
