"""Converting broker *server time* (what MT5 reports show) to UTC.

MT5 history reports carry no timezone: times are in the broker server's clock. Two kinds of
rule are supported:

* ``ny_close``: the common "New York close" server clock, always New York time + 7 hours
  (UTC+2 in winter, UTC+3 in summer, switching on the *US* daylight-saving dates). This
  differs from a fixed European zone for a few weeks each spring and autumn.
* any IANA zone name, e.g. ``UTC`` or ``Europe/Athens``.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

NY_CLOSE = "ny_close"
_NEW_YORK = ZoneInfo("America/New_York")
_NY_CLOSE_OFFSET = timedelta(hours=7)


class InvalidServerTimeRule(ValueError):
    pass


def validate_server_time_rule(rule: str) -> str:
    """Return the rule if it is usable, else raise InvalidServerTimeRule."""
    rule = rule.strip()
    if rule == NY_CLOSE:
        return rule
    try:
        ZoneInfo(rule)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise InvalidServerTimeRule(
            f"unknown server time rule {rule!r}; "
            "use 'ny_close' or an IANA name like 'Europe/Athens'"
        ) from exc
    return rule


def server_time_to_utc(naive: datetime, rule: str) -> datetime:
    """Convert a naive server-clock datetime to timezone-aware UTC.

    Wall-clock times that are ambiguous or skipped at a DST change resolve to the first
    occurrence; markets are closed at those moments, so no real trade lands there.
    """
    if naive.tzinfo is not None:
        raise ValueError("expected a naive datetime in server time")
    if rule == NY_CLOSE:
        return (naive - _NY_CLOSE_OFFSET).replace(tzinfo=_NEW_YORK).astimezone(UTC)
    return naive.replace(tzinfo=ZoneInfo(rule)).astimezone(UTC)
