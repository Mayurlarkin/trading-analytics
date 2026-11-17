"""What the analytics endpoints return.

Money is sent as strings rounded to 2 decimals ("-1234.50"), never as floating-point numbers,
so no client can lose a cent to rounding. Ratios and percentages are fractions rounded to 4
decimals (0.2500 means 25%). Times are UTC.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel

from app.analytics import Drawdown, EquityPoint, Group, Streak, Summary, TradeStats

_MONEY = Decimal("0.01")
_FRACTION = Decimal("0.0001")


def _money(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(_MONEY, ROUND_HALF_UP)


def _fraction(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(_FRACTION, ROUND_HALF_UP)


class UserOut(BaseModel):
    id: int
    email: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # seconds


class AccountOut(BaseModel):
    id: int
    label: str
    broker: str | None
    currency: str
    starting_balance: Decimal
    is_demo: bool
    server_timezone: str | None
    trade_count: int
    last_close_time: datetime | None


class StreakOut(BaseModel):
    count: int
    amount: Decimal

    @classmethod
    def of(cls, streak: Streak) -> "StreakOut":
        return cls(count=streak.count, amount=_money(streak.amount))  # type: ignore[arg-type]


class TradeStatsOut(BaseModel):
    trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: Decimal | None
    gross_profit: Decimal
    gross_loss: Decimal
    net_profit: Decimal
    total_commission: Decimal
    total_swap: Decimal
    profit_factor: Decimal | None
    expectancy: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    payoff_ratio: Decimal | None
    largest_win: Decimal | None
    largest_loss: Decimal | None
    longest_win_streak: StreakOut
    longest_loss_streak: StreakOut
    average_holding_seconds: int | None

    @classmethod
    def of(cls, s: TradeStats) -> "TradeStatsOut":
        holding = s.average_holding_time
        return cls(
            trades=s.trades,
            wins=s.wins,
            losses=s.losses,
            breakeven=s.breakeven,
            win_rate=_fraction(s.win_rate),
            gross_profit=_money(s.gross_profit),  # type: ignore[arg-type]
            gross_loss=_money(s.gross_loss),  # type: ignore[arg-type]
            net_profit=_money(s.net_profit),  # type: ignore[arg-type]
            total_commission=_money(s.total_commission),  # type: ignore[arg-type]
            total_swap=_money(s.total_swap),  # type: ignore[arg-type]
            profit_factor=_fraction(s.profit_factor),
            expectancy=_money(s.expectancy),
            average_win=_money(s.average_win),
            average_loss=_money(s.average_loss),
            payoff_ratio=_fraction(s.payoff_ratio),
            largest_win=_money(s.largest_win),
            largest_loss=_money(s.largest_loss),
            longest_win_streak=StreakOut.of(s.longest_win_streak),
            longest_loss_streak=StreakOut.of(s.longest_loss_streak),
            average_holding_seconds=None if holding is None else round(holding.total_seconds()),
        )


class DrawdownOut(BaseModel):
    amount: Decimal
    percent: Decimal  # fraction of the peak
    peak: Decimal
    trough: Decimal
    peak_time: datetime | None  # null: the peak was the starting balance
    trough_time: datetime
    recovered_time: datetime | None  # null: not recovered yet

    @classmethod
    def of(cls, d: Drawdown | None) -> "DrawdownOut | None":
        if d is None:
            return None
        return cls(
            amount=_money(d.amount),  # type: ignore[arg-type]
            percent=_fraction(d.percent),  # type: ignore[arg-type]
            peak=_money(d.peak),  # type: ignore[arg-type]
            trough=_money(d.trough),  # type: ignore[arg-type]
            peak_time=d.peak_time,
            trough_time=d.trough_time,
            recovered_time=d.recovered_time,
        )


class SummaryOut(BaseModel):
    currency: str
    closed_from: datetime | None
    closed_until: datetime | None
    starting_balance: Decimal  # the balance at the start of the period
    ending_balance: Decimal
    return_pct: Decimal | None
    stats: TradeStatsOut
    max_drawdown: DrawdownOut | None
    max_drawdown_relative: DrawdownOut | None
    absolute_drawdown: Decimal
    recovery_factor: Decimal | None

    @classmethod
    def of(
        cls,
        summary: Summary,
        *,
        currency: str,
        closed_from: datetime | None,
        closed_until: datetime | None,
    ) -> "SummaryOut":
        return cls(
            currency=currency,
            closed_from=closed_from,
            closed_until=closed_until,
            starting_balance=_money(summary.starting_balance),  # type: ignore[arg-type]
            ending_balance=_money(summary.ending_balance),  # type: ignore[arg-type]
            return_pct=_fraction(summary.return_pct),
            stats=TradeStatsOut.of(summary.stats),
            max_drawdown=DrawdownOut.of(summary.max_drawdown),
            max_drawdown_relative=DrawdownOut.of(summary.max_drawdown_relative),
            absolute_drawdown=_money(summary.absolute_drawdown),  # type: ignore[arg-type]
            recovery_factor=_fraction(summary.recovery_factor),
        )


class EquityPointOut(BaseModel):
    time: datetime
    ticket: int
    balance: Decimal
    peak: Decimal
    drawdown: Decimal
    drawdown_pct: Decimal

    @classmethod
    def of(cls, p: EquityPoint) -> "EquityPointOut":
        return cls(
            time=p.time,
            ticket=p.ticket,
            balance=_money(p.balance),  # type: ignore[arg-type]
            peak=_money(p.peak),  # type: ignore[arg-type]
            drawdown=_money(p.drawdown),  # type: ignore[arg-type]
            drawdown_pct=_fraction(p.drawdown_pct),  # type: ignore[arg-type]
        )


class EquityCurveOut(BaseModel):
    currency: str
    starting_balance: Decimal  # the balance before the first point
    points: list[EquityPointOut]


class GroupOut(BaseModel):
    key: str
    stats: TradeStatsOut

    @classmethod
    def of(cls, g: Group) -> "GroupOut":
        return cls(key=g.key, stats=TradeStatsOut.of(g.stats))


class BreakdownOut(BaseModel):
    by: Literal["instrument", "session", "weekday", "hour"]
    timezone: str | None  # the clock used for session/weekday/hour; null for instrument
    currency: str
    groups: list[GroupOut]


class TradeOut(BaseModel):
    ticket: int
    symbol: str  # as the broker names it
    instrument: str  # the common name, e.g. NAS100
    direction: Literal["buy", "sell"]
    volume: Decimal
    open_time: datetime
    close_time: datetime
    open_price: Decimal
    close_price: Decimal
    sl: Decimal | None
    tp: Decimal | None
    commission: Decimal
    swap: Decimal
    profit: Decimal
    net: Decimal  # profit + commission + swap
    strategy_tag: str | None


class TradesPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[TradeOut]
