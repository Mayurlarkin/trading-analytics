from datetime import UTC, datetime

import pytest

from app.timezones import (
    NY_CLOSE,
    InvalidServerTimeRule,
    server_time_to_utc,
    validate_server_time_rule,
)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


@pytest.mark.parametrize(
    ("server_time", "expected_utc", "why"),
    [
        # US standard time (NY = UTC-5): server = UTC+2
        (datetime(2026, 3, 3, 9, 30, 15), utc(2026, 3, 3, 7, 30, 15), "early March, winter"),
        (datetime(2026, 11, 15, 19, 25), utc(2026, 11, 15, 17, 25), "mid November, winter"),
        # US daylight time (NY = UTC-4): server = UTC+3
        (datetime(2026, 7, 1, 12, 0), utc(2026, 7, 1, 9, 0), "mid summer"),
        # 10 March: US DST started on 8 March but EU DST not until 29 March. A fixed
        # European zone would be an hour out here; the NY-based rule is not.
        (datetime(2026, 3, 10, 14, 20, 45), utc(2026, 3, 10, 11, 20, 45), "US-only DST window"),
        # 28 October: EU DST ended on 25 October but US DST runs until 1 November.
        (datetime(2026, 10, 28, 14, 0), utc(2026, 10, 28, 11, 0), "EU-ended, US-still-DST window"),
    ],
)
def test_ny_close_follows_us_daylight_saving(server_time, expected_utc, why) -> None:
    assert server_time_to_utc(server_time, NY_CLOSE) == expected_utc, why


def test_a_european_zone_disagrees_in_the_us_only_dst_window() -> None:
    server_time = datetime(2026, 3, 10, 14, 20, 45)
    assert server_time_to_utc(server_time, "Europe/Athens") != server_time_to_utc(
        server_time, NY_CLOSE
    )


def test_iana_zone_and_utc_rules() -> None:
    assert server_time_to_utc(datetime(2026, 1, 5, 10, 0), "UTC") == utc(2026, 1, 5, 10, 0)
    assert server_time_to_utc(datetime(2026, 1, 5, 10, 0), "Europe/Athens") == utc(2026, 1, 5, 8, 0)


def test_result_is_timezone_aware_utc() -> None:
    result = server_time_to_utc(datetime(2026, 7, 1, 12, 0), NY_CLOSE)
    assert result.utcoffset().total_seconds() == 0


def test_aware_input_is_refused() -> None:
    with pytest.raises(ValueError, match="naive"):
        server_time_to_utc(utc(2026, 1, 1), NY_CLOSE)


def test_rule_validation() -> None:
    assert validate_server_time_rule(" ny_close ") == "ny_close"
    assert validate_server_time_rule("Europe/Athens") == "Europe/Athens"
    for bad in ("", "Mars/Olympus", "ny+7", "../etc/passwd"):
        with pytest.raises(InvalidServerTimeRule):
            validate_server_time_rule(bad)
