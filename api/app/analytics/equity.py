from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.analytics.trade import ZERO, ClosedTrade


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """The account balance right after one trade closed.

    This is a *closed-trade* curve: it moves only when a position closes, so it ignores the
    floating profit and loss of positions still open. ``drawdown_pct`` is a fraction (0.25 = 25%).
    """

    time: datetime
    ticket: int
    balance: Decimal
    peak: Decimal
    drawdown: Decimal
    drawdown_pct: Decimal


@dataclass(frozen=True, slots=True)
class Drawdown:
    """A fall from a peak balance to a later low. ``percent`` is a fraction of the peak."""

    amount: Decimal
    percent: Decimal
    peak: Decimal
    trough: Decimal
    peak_time: datetime | None  # None: the peak was the starting balance
    trough_time: datetime
    recovered_time: datetime | None  # None: the balance has not got back to the peak


def in_close_order(trades: Iterable[ClosedTrade]) -> list[ClosedTrade]:
    """Trades in the order they closed; ties are broken by ticket so results are repeatable."""
    return sorted(trades, key=lambda t: (t.close_time, t.ticket))


def equity_curve(trades: Iterable[ClosedTrade], starting_balance: Decimal) -> list[EquityPoint]:
    balance = peak = starting_balance
    points: list[EquityPoint] = []
    for trade in in_close_order(trades):
        balance += trade.net
        peak = max(peak, balance)
        drawdown = peak - balance
        points.append(
            EquityPoint(
                time=trade.close_time,
                ticket=trade.ticket,
                balance=balance,
                peak=peak,
                drawdown=drawdown,
                drawdown_pct=drawdown / peak if peak > 0 else ZERO,
            )
        )
    return points


def _build_drawdown(
    points: Sequence[EquityPoint], trough_index: int, peak: Decimal, peak_time: datetime | None
) -> Drawdown:
    trough_point = points[trough_index]
    recovered = next((p.time for p in points[trough_index + 1 :] if p.balance >= peak), None)
    return Drawdown(
        amount=peak - trough_point.balance,
        percent=(peak - trough_point.balance) / peak if peak > 0 else ZERO,
        peak=peak,
        trough=trough_point.balance,
        peak_time=peak_time,
        trough_time=trough_point.time,
        recovered_time=recovered,
    )


def max_drawdowns(
    points: Sequence[EquityPoint], starting_balance: Decimal
) -> tuple[Drawdown | None, Drawdown | None]:
    """The deepest drawdown by amount and the deepest by percentage (often the same one).

    The starting balance counts as the first peak. Returns None for either when the balance
    never fell below a previous high. Ties go to the earlier drawdown.
    """
    peak = starting_balance
    peak_time: datetime | None = None
    best_amount: tuple[Decimal, int, Decimal, datetime | None] | None = None
    best_percent: tuple[Decimal, int, Decimal, datetime | None] | None = None

    for index, point in enumerate(points):
        if point.balance > peak:
            peak, peak_time = point.balance, point.time
            continue
        amount = peak - point.balance
        if amount <= 0:
            continue
        percent = amount / peak if peak > 0 else ZERO
        if best_amount is None or amount > best_amount[0]:
            best_amount = (amount, index, peak, peak_time)
        if best_percent is None or percent > best_percent[0]:
            best_percent = (percent, index, peak, peak_time)

    def build(best: tuple[Decimal, int, Decimal, datetime | None] | None) -> Drawdown | None:
        return None if best is None else _build_drawdown(points, best[1], best[2], best[3])

    return build(best_amount), build(best_percent)
