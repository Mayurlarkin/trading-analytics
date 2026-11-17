from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analytics import (
    ClosedTrade,
    Session,
    by_hour,
    by_instrument,
    by_session,
    by_weekday,
    canonical_symbol,
)

D = Decimal


def opened(ticket: int, when: str, net: int = 10, symbol: str = "NAS100") -> ClosedTrade:
    start = datetime.fromisoformat(when).replace(tzinfo=UTC)
    return ClosedTrade(ticket, symbol, "buy", start, start + timedelta(minutes=30), D(net))


# New York is UTC-5 until 8 March 2026 and UTC-4 after it.
MON_0930 = opened(1, "2026-03-02T14:30")  # Monday 09:30 New York
MON_1700 = opened(2, "2026-03-02T22:00")  # Monday 17:00
MON_2000 = opened(3, "2026-03-03T01:00")  # Tuesday in UTC, but Monday 20:00 in New York
TUE_0130 = opened(4, "2026-03-03T06:30")  # Tuesday 01:30
WED_0215 = opened(5, "2026-07-01T06:15")  # Wednesday 02:15 (summer time)
FRI_1030 = opened(6, "2026-07-03T14:30")  # same UTC clock as MON_0930, but 10:30 New York
ALL = [MON_0930, MON_1700, MON_2000, TUE_0130, WED_0215, FRI_1030]


def counts(groups) -> dict[str, int]:
    return {g.key: g.stats.trades for g in groups if g.stats.trades}


def test_weekdays_follow_the_new_york_clock_not_utc() -> None:
    groups = by_weekday(ALL)
    assert [g.key for g in groups] == [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    ]  # fmt: skip
    # MON_2000 is Tuesday in UTC but belongs to Monday in New York
    assert counts(groups) == {"Monday": 3, "Tuesday": 1, "Wednesday": 1, "Friday": 1}


def test_a_different_clock_can_be_chosen() -> None:
    assert counts(by_weekday([MON_2000], tz="UTC")) == {"Tuesday": 1}


def test_hours_include_every_hour_and_respect_summer_time() -> None:
    groups = by_hour(ALL)
    assert [g.key for g in groups] == [f"{h:02d}" for h in range(24)]
    assert counts(groups) == {"01": 1, "02": 1, "09": 1, "10": 1, "17": 1, "20": 1}


def test_sessions_including_the_one_that_wraps_past_midnight() -> None:
    groups = by_session(ALL)
    assert [g.key for g in groups] == [
        "Asia", "London", "New York AM", "New York PM", "After hours",
    ]  # fmt: skip
    assert counts(groups) == {
        "Asia": 2,  # 20:00 and 01:30
        "London": 1,  # 02:15
        "New York AM": 2,  # 09:30 and 10:30
        "After hours": 1,  # 17:00
    }


def test_session_boundaries_are_start_inclusive_end_exclusive() -> None:
    asia = Session("Asia", 19, 2)
    assert [h for h in range(24) if asia.contains(h)] == [0, 1, 19, 20, 21, 22, 23]
    day = Session("Day", 9, 17)
    assert day.contains(9) and day.contains(16) and not day.contains(17)


def test_hours_no_session_covers_go_to_other() -> None:
    groups = by_session(ALL, sessions=[Session("US day", 9, 17)])
    assert [g.key for g in groups] == ["US day", "Other"]
    assert counts(groups) == {"US day": 2, "Other": 4}


def test_each_group_carries_full_statistics() -> None:
    win = opened(1, "2026-03-02T14:30", net=100)
    loss = opened(2, "2026-03-02T15:30", net=-40)
    (monday,) = [g for g in by_weekday([win, loss]) if g.key == "Monday"]
    assert (monday.stats.trades, monday.stats.net_profit) == (2, 60)
    assert monday.stats.profit_factor == D("2.5")
    empty = [g for g in by_weekday([win, loss]) if g.key == "Sunday"][0]
    assert empty.stats.trades == 0 and empty.stats.win_rate is None


def test_instruments_are_ordered_by_net_result() -> None:
    trades = [
        opened(1, "2026-03-02T14:30", 100, "NAS100"),
        opened(2, "2026-03-02T14:40", -30, "US30"),
        opened(3, "2026-03-02T14:50", 20, "XAUUSD"),
        opened(4, "2026-03-02T15:00", 20, "BTCUSD"),
        opened(5, "2026-03-02T15:10", 5, "US30"),
    ]
    groups = by_instrument(trades)
    assert [(g.key, g.stats.net_profit) for g in groups] == [
        ("NAS100", 100), ("BTCUSD", 20), ("XAUUSD", 20), ("US30", -25),
    ]  # fmt: skip


def test_canonical_symbols() -> None:
    assert canonical_symbol("T100.IFX_M") == "NAS100"
    assert canonical_symbol("WS30.ifx_m") == "US30"
    assert canonical_symbol("XAUUSD.ifx") == "XAUUSD"
    assert canonical_symbol("XBTUSD.IFX") == "BTCUSD"
    assert canonical_symbol(" eurusd ") == "EURUSD"
    assert canonical_symbol("GER40.cash") == "GER40"
