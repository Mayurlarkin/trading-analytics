"""Golden tests: every expected number below was worked out by hand (see the comments)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.analytics import ClosedTrade, Streak, equity_curve, max_drawdowns, summarize, trade_stats

D = Decimal
T0 = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)


def trade(
    n: int,
    net: str | int,
    *,
    holding_minutes: int = 60,
    commission: str | int = 0,
    swap: str | int = 0,
    close: datetime | None = None,
) -> ClosedTrade:
    """Trade number n, closing n days after T0, with profit set so that net comes out as given."""
    closed = close or T0 + timedelta(days=n)
    return ClosedTrade(
        ticket=n,
        symbol="NAS100",
        direction="buy",
        open_time=closed - timedelta(minutes=holding_minutes),
        close_time=closed,
        profit=D(net) - D(commission) - D(swap),
        commission=D(commission),
        swap=D(swap),
    )


# Start 1000. Results 100, -50, -30, 200, -400, 50, 0, 10.
# Balances      1100, 1050, 1020, 1220, 820, 870, 870, 880   (peak 1220 after trade 4)
NETS = [100, -50, -30, 200, -400, 50, 0, 10]
HOLDINGS = [60, 30, 30, 120, 15, 45, 60, 0]  # sum 360 minutes, so the average is 45
GOLDEN = [
    trade(n, net, holding_minutes=h)
    for n, (net, h) in enumerate(zip(NETS, HOLDINGS, strict=True), start=1)
]


def test_counts_and_sums() -> None:
    s = trade_stats(GOLDEN)
    assert (s.trades, s.wins, s.losses, s.breakeven) == (8, 4, 3, 1)
    assert s.win_rate == D(4) / 8  # 4 of 8 trades are wins
    assert s.gross_profit == 360  # 100 + 200 + 50 + 10
    assert s.gross_loss == -480  # -50 - 30 - 400
    assert s.net_profit == -120


def test_ratios() -> None:
    s = trade_stats(GOLDEN)
    assert s.profit_factor == D("0.75")  # 360 / 480
    assert s.expectancy == -15  # -120 / 8
    assert s.average_win == 90  # 360 / 4
    assert s.average_loss == -160  # -480 / 3
    assert s.payoff_ratio == D("0.5625")  # 90 / 160
    assert (s.largest_win, s.largest_loss) == (200, -400)
    assert s.average_holding_time == timedelta(minutes=45)


def test_streaks_are_broken_by_the_opposite_result_and_by_break_even() -> None:
    s = trade_stats(GOLDEN)
    # wins never come twice in a row; the first one (+100) is reported when counts tie
    assert s.longest_win_streak == Streak(1, D(100))
    assert s.longest_loss_streak == Streak(2, D(-80))  # -50, -30

    flat = trade_stats([trade(n, v) for n, v in enumerate([1, 1, 0, 1, 1, 1, -1, 0, -1], start=1)])
    assert flat.longest_win_streak == Streak(3, D(3))  # the break-even splits 2+3
    assert flat.longest_loss_streak == Streak(1, D(-1))  # the break-even splits -1 and -1


def test_the_account_summary() -> None:
    s = summarize(GOLDEN, D(1000))
    assert s.ending_balance == 880
    assert s.return_pct == D("-0.12")  # -120 / 1000
    assert s.absolute_drawdown == 180  # 1000 - lowest balance (820)
    deepest = s.max_drawdown
    assert deepest is not None
    assert deepest.amount == 400  # 1220 -> 820
    assert deepest.percent == D(400) / D(1220)
    assert (deepest.peak, deepest.trough) == (1220, 820)
    assert deepest.peak_time == GOLDEN[3].close_time
    assert deepest.trough_time == GOLDEN[4].close_time
    assert deepest.recovered_time is None  # 880 never got back to 1220
    assert s.max_drawdown_relative == deepest  # the same dip is also the deepest in percent
    assert s.recovery_factor == D("-0.3")  # -120 / 400


def test_equity_curve_points() -> None:
    points = equity_curve(GOLDEN, D(1000))
    assert [p.balance for p in points] == [1100, 1050, 1020, 1220, 820, 870, 870, 880]
    assert [p.peak for p in points] == [1100, 1100, 1100, 1220, 1220, 1220, 1220, 1220]
    assert [p.drawdown for p in points] == [0, 50, 80, 0, 400, 350, 350, 340]
    assert points[2].drawdown_pct == D(80) / D(1100)
    assert points[4].time == GOLDEN[4].close_time


def test_deepest_by_amount_and_by_percent_can_be_different_dips() -> None:
    # Start 100. -50 -> 50 (a 50% drop, only 50 in money), +950 -> 1000, -200 -> 800 (20%).
    trades = [trade(1, -50), trade(2, 950), trade(3, -200)]
    by_amount, by_percent = max_drawdowns(equity_curve(trades, D(100)), D(100))
    assert by_amount is not None and by_percent is not None

    assert by_amount.amount == 200
    assert by_amount.percent == D("0.2")
    assert by_amount.peak_time == trades[1].close_time
    assert by_amount.recovered_time is None

    assert by_percent.percent == D("0.5")
    assert by_percent.amount == 50
    assert by_percent.peak_time is None  # the peak was the starting balance
    assert by_percent.recovered_time == trades[1].close_time  # 1000 >= 100


def test_costs_decide_whether_a_trade_won() -> None:
    # Profit +2 but commission -3: the trade really lost 1.
    s = trade_stats([trade(1, -1, commission=-3), trade(2, 5, swap=-1)])
    assert (s.wins, s.losses) == (1, 1)
    assert s.net_profit == 4
    assert s.total_commission == -3
    assert s.total_swap == -1


def test_no_trades() -> None:
    s = summarize([], D(1000))
    assert s.stats.trades == 0
    assert s.stats.win_rate is None and s.stats.expectancy is None
    assert s.stats.profit_factor is None and s.stats.average_holding_time is None
    assert s.stats.longest_win_streak == Streak(0, D(0))
    assert (s.ending_balance, s.absolute_drawdown) == (1000, 0)
    assert s.max_drawdown is None and s.recovery_factor is None
    assert s.return_pct == 0


def test_only_winners_have_no_profit_factor_and_no_drawdown() -> None:
    s = summarize([trade(1, 10), trade(2, 20)], D(100))
    assert s.stats.profit_factor is None  # nothing was lost, so the ratio is undefined
    assert s.stats.average_loss is None and s.stats.payoff_ratio is None
    assert s.max_drawdown is None and s.max_drawdown_relative is None
    assert s.absolute_drawdown == 0


def test_a_single_losing_trade() -> None:
    s = summarize([trade(1, -25)], D(100))
    assert s.stats.profit_factor == 0
    assert s.max_drawdown is not None and s.max_drawdown.percent == D("0.25")
    assert s.recovery_factor == -1


def test_order_of_the_input_does_not_matter() -> None:
    assert summarize(list(reversed(GOLDEN)), D(1000)) == summarize(GOLDEN, D(1000))


def test_trades_closing_at_the_same_moment_are_ordered_by_ticket() -> None:
    moment = T0 + timedelta(days=1)
    a = trade(2, -100, close=moment)
    b = trade(1, 300, close=moment)
    assert [p.ticket for p in equity_curve([a, b], D(1000))] == [1, 2]


def test_a_zero_starting_balance_does_not_divide_by_zero() -> None:
    s = summarize([trade(1, -10), trade(2, 4)], D(0))
    assert s.return_pct is None
    assert s.max_drawdown is not None and s.max_drawdown.percent == 0
    assert s.absolute_drawdown == 10


def test_naive_times_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        ClosedTrade(1, "X", "buy", datetime(2026, 1, 1), datetime(2026, 1, 2), D(1))
