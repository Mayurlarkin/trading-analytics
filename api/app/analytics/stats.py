from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from app.analytics.equity import Drawdown, equity_curve, in_close_order, max_drawdowns
from app.analytics.trade import ZERO, ClosedTrade


@dataclass(frozen=True, slots=True)
class Streak:
    """A run of consecutive wins or losses: how many, and what they added up to."""

    count: int
    amount: Decimal


@dataclass(frozen=True, slots=True)
class TradeStats:
    """Everything that can be said about a set of trades without an account balance.

    A win is a trade whose net result is above zero, a loss one below zero; exactly zero is
    break-even. Ratios that cannot be calculated (no losing trade, no trades) are None.
    Fractions (win_rate) are 0..1.
    """

    trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: Decimal | None
    gross_profit: Decimal
    gross_loss: Decimal  # zero or negative
    net_profit: Decimal
    total_commission: Decimal
    total_swap: Decimal
    profit_factor: Decimal | None  # gross profit / gross loss
    expectancy: Decimal | None  # average net result per trade
    average_win: Decimal | None
    average_loss: Decimal | None  # negative
    payoff_ratio: Decimal | None  # average win / average loss
    largest_win: Decimal | None
    largest_loss: Decimal | None
    longest_win_streak: Streak
    longest_loss_streak: Streak
    average_holding_time: timedelta | None


@dataclass(frozen=True, slots=True)
class Summary:
    """Trade statistics plus the account-level numbers that need a starting balance."""

    stats: TradeStats
    starting_balance: Decimal
    ending_balance: Decimal
    return_pct: Decimal | None  # net profit / starting balance, as a fraction
    max_drawdown: Drawdown | None  # deepest by amount
    max_drawdown_relative: Drawdown | None  # deepest by percentage
    absolute_drawdown: Decimal  # starting balance minus the lowest balance reached (>= 0)
    recovery_factor: Decimal | None  # net profit / deepest drawdown amount


def _longest_streak(results: Sequence[Decimal], *, winning: bool) -> Streak:
    best = Streak(0, ZERO)
    count, amount = 0, ZERO
    for result in results:
        in_run = result > 0 if winning else result < 0
        if in_run:
            count += 1
            amount += result
            if count > best.count:
                best = Streak(count, amount)
        else:  # a loss ends a winning run, a win ends a losing run, break-even ends both
            count, amount = 0, ZERO
    return best


def trade_stats(trades: Iterable[ClosedTrade]) -> TradeStats:
    ordered = in_close_order(trades)
    results = [t.net for t in ordered]
    wins = [r for r in results if r > 0]
    losses = [r for r in results if r < 0]
    gross_profit = sum(wins, ZERO)
    gross_loss = sum(losses, ZERO)
    count = len(ordered)
    net = gross_profit + gross_loss
    average_win = gross_profit / len(wins) if wins else None
    average_loss = gross_loss / len(losses) if losses else None
    return TradeStats(
        trades=count,
        wins=len(wins),
        losses=len(losses),
        breakeven=count - len(wins) - len(losses),
        win_rate=Decimal(len(wins)) / count if count else None,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=net,
        total_commission=sum((t.commission for t in ordered), ZERO),
        total_swap=sum((t.swap for t in ordered), ZERO),
        profit_factor=gross_profit / -gross_loss if gross_loss < 0 else None,
        expectancy=net / count if count else None,
        average_win=average_win,
        average_loss=average_loss,
        payoff_ratio=(
            average_win / -average_loss if average_win is not None and average_loss else None
        ),
        largest_win=max(wins) if wins else None,
        largest_loss=min(losses) if losses else None,
        longest_win_streak=_longest_streak(results, winning=True),
        longest_loss_streak=_longest_streak(results, winning=False),
        average_holding_time=(
            sum((t.holding_time for t in ordered), timedelta()) / count if count else None
        ),
    )


def summarize(trades: Iterable[ClosedTrade], starting_balance: Decimal) -> Summary:
    ordered = in_close_order(trades)
    stats = trade_stats(ordered)
    points = equity_curve(ordered, starting_balance)
    deepest, deepest_relative = max_drawdowns(points, starting_balance)
    lowest = min((p.balance for p in points), default=starting_balance)
    return Summary(
        stats=stats,
        starting_balance=starting_balance,
        ending_balance=points[-1].balance if points else starting_balance,
        return_pct=stats.net_profit / starting_balance if starting_balance > 0 else None,
        max_drawdown=deepest,
        max_drawdown_relative=deepest_relative,
        absolute_drawdown=max(ZERO, starting_balance - lowest),
        recovery_factor=stats.net_profit / deepest.amount if deepest else None,
    )
