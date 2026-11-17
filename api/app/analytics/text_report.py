"""A plain-text rendering of the analytics, for the command line (and anywhere a quick
readable summary is wanted). The web dashboard will use the structured data instead."""

from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

from app.analytics.breakdowns import Group
from app.analytics.equity import Drawdown
from app.analytics.stats import Streak, Summary


def money(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value:,.2f}"


def percent(fraction: Decimal | None) -> str:
    return "n/a" if fraction is None else f"{fraction * 100:.2f}%"


def ratio(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def duration(value: timedelta | None) -> str:
    if value is None:
        return "n/a"
    days, rest = divmod(int(value.total_seconds() // 60), 1440)
    hours, minutes = divmod(rest, 60)
    parts = [f"{days}d" if days else "", f"{hours}h" if hours else ""]
    parts.append(f"{minutes}m" if minutes or not (days or hours) else "")
    return " ".join(part for part in parts if part)


def _drawdown_line(dd: Drawdown | None, currency: str) -> str:
    if dd is None:
        return "none"
    start = dd.peak_time.strftime("%Y-%m-%d") if dd.peak_time else "start"
    end = dd.trough_time.strftime("%Y-%m-%d")
    back = dd.recovered_time.strftime("%Y-%m-%d") if dd.recovered_time else "not recovered"
    return f"{money(dd.amount)} {currency} ({percent(dd.percent)}), {start} to {end}, {back}"


def _streak(streak: Streak) -> str:
    return f"{streak.count} ({money(streak.amount)})"


def format_summary(label: str, currency: str, summary: Summary) -> str:
    s = summary.stats
    balance = f"{money(summary.starting_balance)} -> {money(summary.ending_balance)} {currency}"
    rows = [
        ("Trades", f"{s.trades} ({s.wins} wins, {s.losses} losses, {s.breakeven} break-even)"),
        ("Win rate", percent(s.win_rate)),
        ("Net profit", f"{money(s.net_profit)} {currency} ({percent(summary.return_pct)} return)"),
        ("Gross profit / loss", f"{money(s.gross_profit)} / {money(s.gross_loss)}"),
        ("Commission / swap", f"{money(s.total_commission)} / {money(s.total_swap)}"),
        ("Profit factor", ratio(s.profit_factor)),
        ("Expectancy per trade", money(s.expectancy)),
        ("Average win / loss", f"{money(s.average_win)} / {money(s.average_loss)}"),
        ("Payoff ratio", ratio(s.payoff_ratio)),
        ("Largest win / loss", f"{money(s.largest_win)} / {money(s.largest_loss)}"),
        ("Longest win streak", _streak(s.longest_win_streak)),
        ("Longest loss streak", _streak(s.longest_loss_streak)),
        ("Average holding time", duration(s.average_holding_time)),
        ("Balance", balance),
        ("Max drawdown", _drawdown_line(summary.max_drawdown, currency)),
        ("Max drawdown (%)", _drawdown_line(summary.max_drawdown_relative, currency)),
        ("Absolute drawdown", f"{money(summary.absolute_drawdown)} {currency}"),
        ("Recovery factor", ratio(summary.recovery_factor)),
    ]  # fmt: skip
    width = max(len(name) for name, _ in rows)
    lines = [f"{label} ({currency})", ""]
    lines += [f"{name:<{width}}  {value}" for name, value in rows]
    return "\n".join(lines)


def format_groups(title: str, groups: Sequence[Group]) -> str:
    """A small table; groups with no trades are left out."""
    used = [g for g in groups if g.stats.trades]
    if not used:
        return f"{title}\n  (no trades)"
    key_width = max(len(title), *(len(g.key) for g in used))
    header = f"{title:<{key_width}}  {'trades':>6}  {'win %':>7}  {'net':>14}  {'PF':>6}"
    lines = [header, "-" * len(header)]
    for g in used:
        st = g.stats
        lines.append(
            f"{g.key:<{key_width}}  {st.trades:>6}  {percent(st.win_rate):>7}  "
            f"{money(st.net_profit):>14}  {ratio(st.profit_factor):>6}"
        )
    return "\n".join(lines)
