// What the API returns. Money arrives as strings ("-1234.50") and ratios as fractions
// ("0.2500" is 25%), so nothing is lost on the way; convert only to display or to draw.

export interface User {
  id: number
  email: string
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export interface Account {
  id: number
  label: string
  broker: string | null
  currency: string
  starting_balance: string
  is_demo: boolean
  server_timezone: string | null
  trade_count: number
  last_close_time: string | null
}

export interface AccountCreate {
  label: string
  broker?: string | null
  currency: string
  starting_balance: string
  is_demo: boolean
  server_timezone?: string | null
}

export interface Streak {
  count: number
  amount: string
}

export interface TradeStats {
  trades: number
  wins: number
  losses: number
  breakeven: number
  win_rate: string | null
  gross_profit: string
  gross_loss: string
  net_profit: string
  total_commission: string
  total_swap: string
  profit_factor: string | null
  expectancy: string | null
  average_win: string | null
  average_loss: string | null
  payoff_ratio: string | null
  largest_win: string | null
  largest_loss: string | null
  longest_win_streak: Streak
  longest_loss_streak: Streak
  average_holding_seconds: number | null
}

export interface Drawdown {
  amount: string
  percent: string
  peak: string
  trough: string
  peak_time: string | null
  trough_time: string
  recovered_time: string | null
}

export interface Summary {
  currency: string
  closed_from: string | null
  closed_until: string | null
  starting_balance: string
  ending_balance: string
  return_pct: string | null
  stats: TradeStats
  max_drawdown: Drawdown | null
  max_drawdown_relative: Drawdown | null
  absolute_drawdown: string
  recovery_factor: string | null
}

export interface EquityPoint {
  time: string
  ticket: number
  balance: string
  peak: string
  drawdown: string
  drawdown_pct: string
}

export interface EquityCurve {
  currency: string
  starting_balance: string
  points: EquityPoint[]
}
