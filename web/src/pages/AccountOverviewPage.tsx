import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../api/http'
import { useAccount, useEquityCurve, useSummary } from '../api/queries'
import type { Summary } from '../api/types'
import { PeriodFilter } from '../components/PeriodFilter'
import { StatTile } from '../components/StatTile'
import { TimeSeriesChart, type SeriesPoint } from '../components/charts/TimeSeriesChart'
import {
  NO_VALUE,
  formatDate,
  formatDuration,
  formatMoney,
  formatPercent,
  formatRatio,
  formatSignedMoney,
  formatSignedPercent,
  formatTick,
  toNumber,
} from '../lib/format'
import type { PeriodKey } from '../lib/period'

function tone(value: string | null | undefined): 'good' | 'bad' | undefined {
  const n = toNumber(value)
  if (n === null || n === 0) return undefined
  return n > 0 ? 'good' : 'bad'
}

function Tiles({ summary }: { summary: Summary }) {
  const { stats, max_drawdown: drawdown, currency } = summary
  const money = (value: string | null) =>
    value === null ? NO_VALUE : `${formatSignedMoney(value)} ${currency}`

  return (
    <dl className="tiles">
      <StatTile
        label="Return"
        value={formatSignedPercent(summary.return_pct)}
        tone={tone(summary.return_pct)}
        sub={`on ${formatMoney(summary.starting_balance)} ${currency}`}
      />
      <StatTile
        label="Win rate"
        value={formatPercent(stats.win_rate)}
        sub={`${stats.wins} wins · ${stats.losses} losses${stats.breakeven ? ` · ${stats.breakeven} even` : ''}`}
      />
      <StatTile
        label="Profit factor"
        value={stats.profit_factor === null ? (stats.trades ? 'No losses' : NO_VALUE) : formatRatio(stats.profit_factor)}
        sub="gross profit ÷ gross loss"
      />
      <StatTile
        label="Expectancy"
        value={money(stats.expectancy)}
        tone={tone(stats.expectancy)}
        sub="average result per trade"
      />
      <StatTile label="Average win" value={money(stats.average_win)} sub={`largest ${money(stats.largest_win)}`} />
      <StatTile label="Average loss" value={money(stats.average_loss)} sub={`largest ${money(stats.largest_loss)}`} />
      <StatTile
        label="Max drawdown"
        value={drawdown ? formatPercent(drawdown.percent) : NO_VALUE}
        sub={
          drawdown
            ? `${formatMoney(drawdown.amount)} ${currency} · ${
                drawdown.recovered_time ? `recovered ${formatDate(drawdown.recovered_time)}` : 'not recovered'
              }`
            : undefined
        }
      />
      <StatTile
        label="Average holding time"
        value={formatDuration(stats.average_holding_seconds)}
        sub={`longest losing streak ${stats.longest_loss_streak.count}`}
      />
    </dl>
  )
}

export function AccountOverviewPage() {
  const params = useParams()
  const id = Number(params.id)
  const [period, setPeriod] = useState<PeriodKey>('all')

  const account = useAccount(id)
  const summary = useSummary(id, period)
  const curve = useEquityCurve(id, period)

  const equityPoints = useMemo<SeriesPoint[]>(
    () =>
      (curve.data?.points ?? []).map((p) => ({
        time: Date.parse(p.time),
        value: Number(p.balance),
        detail: `Trade #${p.ticket}`,
      })),
    [curve.data],
  )
  const drawdownPoints = useMemo<SeriesPoint[]>(
    () =>
      (curve.data?.points ?? []).map((p) => ({
        time: Date.parse(p.time),
        value: -Number(p.drawdown_pct) * 100,
        detail: `Trade #${p.ticket}`,
      })),
    [curve.data],
  )

  if (account.isError) {
    const missing = account.error instanceof ApiError && account.error.status === 404
    return (
      <>
        <p>
          <Link to="/">← Accounts</Link>
        </p>
        <p role="alert" className="error">
          {missing ? 'That account does not exist.' : `Could not load the account: ${account.error.message}`}
        </p>
      </>
    )
  }
  if (account.isPending) return <p className="muted">Loading…</p>

  const acct = account.data
  const currency = acct.currency
  const stats = summary.data?.stats
  const refreshing = summary.isPlaceholderData || curve.isPlaceholderData
  const hasNoTradesAtAll = acct.trade_count === 0
  const firstTime = equityPoints[0]?.time
  const lastTime = equityPoints[equityPoints.length - 1]?.time

  return (
    <>
      <p>
        <Link to="/">← Accounts</Link>
      </p>
      <div className="page-head">
        <div>
          <h1>{acct.label}</h1>
          <p className="muted">
            {[acct.broker, acct.is_demo ? 'Demo' : 'Live', currency].filter(Boolean).join(' · ')}
          </p>
        </div>
      </div>

      {hasNoTradesAtAll ? (
        <div className="card empty">
          <h2>No trades yet</h2>
          <p>
            Bring this account&apos;s history in with an MT5 report (<code>POST /import/mt5-report</code>)
            or the reporter EA, then come back here. The dashboard import page is the next piece of
            this project.
          </p>
        </div>
      ) : (
        <>
          <PeriodFilter value={period} onChange={setPeriod} />

          {(summary.isError || curve.isError) && (
            <p role="alert" className="error">
              Could not load the figures: {(summary.error ?? curve.error)?.message}{' '}
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  void summary.refetch()
                  void curve.refetch()
                }}
              >
                Try again
              </button>
            </p>
          )}

          {summary.isPending && !summary.isError && <p className="muted">Loading figures…</p>}

          {summary.data && stats && (
            <div className={refreshing ? 'is-refreshing' : undefined} aria-busy={refreshing}>
              {stats.trades === 0 ? (
                <div className="card empty">
                  <h2>No trades closed in this period</h2>
                  <p>Choose a longer period to see more.</p>
                </div>
              ) : (
                <>
                  <section className="hero" aria-label="Net profit">
                    <p className="hero-label">Net profit</p>
                    <p className={`hero-value tone-${tone(stats.net_profit) ?? 'none'}`}>
                      {formatSignedMoney(stats.net_profit)} <span className="hero-unit">{currency}</span>
                    </p>
                    <p className="muted">
                      {stats.trades} trades
                      {firstTime !== undefined && lastTime !== undefined
                        ? `, closed ${formatDate(firstTime)} to ${formatDate(lastTime)}`
                        : ''}
                    </p>
                  </section>

                  <Tiles summary={summary.data} />

                  {equityPoints.length > 0 && (
                    <>
                      <TimeSeriesChart
                        title={`Account balance (${currency})`}
                        valueLabel="Balance"
                        points={equityPoints}
                        color="var(--series-1)"
                        reference={{ value: Number(curve.data?.starting_balance ?? 0), label: 'Start' }}
                        formatValue={(v) => `${formatMoney(v)} ${currency}`}
                        formatTick={formatTick}
                      />
                      <TimeSeriesChart
                        title="Drawdown from the highest balance"
                        valueLabel="Drawdown"
                        points={drawdownPoints}
                        color="var(--series-2)"
                        height={170}
                        hangingFromZero
                        formatValue={(v) => `${Math.abs(v).toFixed(1)}%`}
                        formatTick={(v) => `${Math.abs(Math.round(v))}%`}
                      />
                    </>
                  )}
                </>
              )}
            </div>
          )}
        </>
      )}
    </>
  )
}
