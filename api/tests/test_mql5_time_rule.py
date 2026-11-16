"""Guards the broker-clock conversion used by the MQL5 reporter (mql5/TradeReporter.mqh).

MetaEditor is not available in CI, so this file holds a line-for-line Python port of the
MQL5 functions NthSunday / IsUsDaylightTime / ToUtc and checks it against the API's own rule
(app.timezones) for every 15 minutes over four years, including the daylight-saving changes.
It proves the algorithm, not the MQL5 syntax: compile the .mqh in MetaEditor to check that.
"""

from datetime import UTC, date, datetime, timedelta

from app.timezones import NY_CLOSE, server_time_to_utc

HOUR = timedelta(hours=1)


def nth_sunday(year: int, month: int, n: int) -> datetime:
    day_of_week = date(year, month, 1).isoweekday() % 7  # MQL5: 0 = Sunday
    day = 1 + (7 - day_of_week) % 7 + 7 * (n - 1)
    return datetime(year, month, day)


def is_us_daylight_time(ny_wall: datetime) -> bool:
    start = nth_sunday(ny_wall.year, 3, 2) + 3 * HOUR
    end = nth_sunday(ny_wall.year, 11, 1) + 2 * HOUR
    return start <= ny_wall < end


def mql5_to_utc(server_time: datetime) -> datetime:
    ny_wall = server_time - 7 * HOUR
    return (ny_wall + (4 if is_us_daylight_time(ny_wall) else 5) * HOUR).replace(tzinfo=UTC)


def test_mql5_algorithm_matches_the_api_rule_for_four_years() -> None:
    moment = datetime(2025, 1, 1)
    end = datetime(2029, 1, 1)
    checked = 0
    while moment < end:
        assert mql5_to_utc(moment) == server_time_to_utc(moment, NY_CLOSE), moment
        moment += timedelta(minutes=15)
        checked += 1
    assert checked > 140_000


def test_the_daylight_saving_dates_the_port_uses_are_the_real_ones() -> None:
    assert nth_sunday(2026, 3, 2) == datetime(2026, 3, 8)
    assert nth_sunday(2026, 11, 1) == datetime(2026, 11, 1)
    assert nth_sunday(2027, 3, 2) == datetime(2027, 3, 14)
    assert nth_sunday(2027, 11, 1) == datetime(2027, 11, 7)
    assert nth_sunday(2028, 3, 2) == datetime(2028, 3, 12)  # March 1st is a Wednesday
    assert nth_sunday(2026, 3, 2) != datetime(2026, 3, 1)  # March 1st 2026 is itself a Sunday
