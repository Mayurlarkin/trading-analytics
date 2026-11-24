import type { Account, EquityCurve, Summary } from '../api/types'

// Invented figures (they are not from any real account).
export const ACCOUNT: Account = {
  id: 1,
  label: 'Demo account',
  broker: 'Example Broker',
  currency: 'ZAR',
  starting_balance: '10000.00',
  is_demo: true,
  server_timezone: 'ny_close',
  trade_count: 9,
  last_close_time: '2026-03-12T12:00:00Z',
}

export const SUMMARY: Summary = {
  currency: 'ZAR',
  closed_from: null,
  closed_until: null,
  starting_balance: '10000.00',
  ending_balance: '9151.38',
  return_pct: '-0.0849',
  stats: {
    trades: 9,
    wins: 5,
    losses: 3,
    breakeven: 1,
    win_rate: '0.5556',
    gross_profit: '456.88',
    gross_loss: '-1305.50',
    net_profit: '-848.62',
    total_commission: '-5.90',
    total_swap: '-13.37',
    profit_factor: '0.3500',
    expectancy: '-94.29',
    average_win: '91.38',
    average_loss: '-326.38',
    payoff_ratio: '0.2800',
    largest_win: '175.00',
    largest_loss: '-992.90',
    longest_win_streak: { count: 2, amount: '225.20' },
    longest_loss_streak: { count: 3, amount: '-6.10' },
    average_holding_seconds: 9001,
  },
  max_drawdown: {
    amount: '1160.32',
    percent: '0.1160',
    peak: '10219.10',
    trough: '9058.78',
    peak_time: '2026-03-04T12:00:00Z',
    trough_time: '2026-03-11T12:00:00Z',
    recovered_time: null,
  },
  max_drawdown_relative: null,
  absolute_drawdown: '941.22',
  recovery_factor: '-0.7314',
}

const NETS = [100, -50, -30, 200, -400, 50, 0, 10, -750]

export function curve(): EquityCurve {
  let balance = 10000
  let peak = balance
  return {
    currency: 'ZAR',
    starting_balance: '10000.00',
    points: NETS.map((net, i) => {
      balance += net
      peak = Math.max(peak, balance)
      return {
        time: new Date(Date.UTC(2026, 2, 4 + i, 12)).toISOString(),
        ticket: 100 + i,
        balance: balance.toFixed(2),
        peak: peak.toFixed(2),
        drawdown: (peak - balance).toFixed(2),
        drawdown_pct: ((peak - balance) / peak).toFixed(4),
      }
    }),
  }
}
