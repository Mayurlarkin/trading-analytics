"""The account endpoints, checked against the hand-worked trade set from the analytics tests.

Start balance 1000. Trades 1-8 close on consecutive days at 12:00 UTC from Tue 3 March 2026
(opened an hour earlier), with results 100, -50, -30, 200, -400, 50, 0, 10.
Trades 1-4 are NAS100 buys (broker name T100.IFX_M), trades 5-8 XAUUSD sells (XAUUSD.ifx).
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.schemas import TradeIn
from app.services.accounts import create_account, update_account
from app.services.ingest import ingest_trades

NETS = [100, -50, -30, 200, -400, 50, 0, 10]
FIRST_CLOSE = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)


def seed(db, account) -> None:
    update_account(db, account.id, starting_balance=Decimal("1000"))
    trades = []
    for n, net in enumerate(NETS, start=1):
        closed = FIRST_CLOSE + timedelta(days=n)
        trades.append(
            TradeIn(
                ticket=n,
                symbol="T100.IFX_M" if n <= 4 else "XAUUSD.ifx",
                direction="buy" if n <= 4 else "sell",
                volume=Decimal("0.10"),
                open_time=closed - timedelta(hours=1),
                close_time=closed,
                open_price=Decimal("100.00"),
                close_price=Decimal("101.00"),
                profit=Decimal(net),
            )
        )
    ingest_trades(db, account, trades)


@pytest.fixture
def seeded(db_session, account_and_key, user_headers) -> dict[str, str]:
    seed(db_session, account_and_key[0])
    return user_headers


def url(account, path: str = "") -> str:
    return f"/accounts/{account.id}{path}"


# --- who can see what -------------------------------------------------------------------


def test_everything_needs_a_login(client, account_and_key) -> None:
    account = account_and_key[0]
    for path in ("", "/summary", "/equity-curve", "/breakdown?by=instrument", "/trades"):
        assert client.get(url(account, path)).status_code == 401, path
    assert client.get("/accounts").status_code == 401


def test_the_list_shows_only_my_accounts(
    client, db_session, account_and_key, user_headers, seeded
) -> None:
    create_account(db_session, email="second@example.com", label="Not mine")

    accounts = client.get("/accounts", headers=seeded).json()

    assert [a["label"] for a in accounts] == ["Test"]
    assert accounts[0]["trade_count"] == 8
    assert accounts[0]["last_close_time"] == "2026-03-10T12:00:00Z"
    assert accounts[0]["starting_balance"] == "1000.00"
    assert "api_key" not in str(accounts[0]).lower()


def test_an_account_with_no_trades_is_listed_with_a_zero_count(
    client, account_and_key, user_headers
) -> None:
    (only,) = client.get("/accounts", headers=user_headers).json()
    assert only["trade_count"] == 0 and only["last_close_time"] is None


def test_someone_elses_account_is_not_found_on_every_endpoint(
    client, db_session, seeded, login_headers: Callable[[str], dict[str, str]]
) -> None:
    mine = client.get("/accounts", headers=seeded).json()[0]["id"]
    create_account(db_session, email="intruder@example.com", label="Other")
    intruder = login_headers("intruder@example.com")

    for path in ("", "/summary", "/equity-curve", "/breakdown?by=hour", "/trades"):
        response = client.get(f"/accounts/{mine}{path}", headers=intruder)
        assert response.status_code == 404, path
        assert response.json() == {"detail": "account not found"}
    assert client.get("/accounts/999999", headers=intruder).status_code == 404  # same answer
    assert client.get("/accounts", headers=intruder).json()[0]["label"] == "Other"


def test_one_account(client, account_and_key, seeded) -> None:
    response = client.get(url(account_and_key[0]), headers=seeded)
    assert response.status_code == 200
    assert response.json()["currency"] == "USD" and response.json()["trade_count"] == 8


# --- summary and equity curve ---------------------------------------------------------------


def test_summary(client, account_and_key, seeded) -> None:
    body = client.get(url(account_and_key[0], "/summary"), headers=seeded).json()

    assert body["currency"] == "USD"
    assert (body["starting_balance"], body["ending_balance"]) == ("1000.00", "880.00")
    assert body["return_pct"] == "-0.1200"
    stats = body["stats"]
    assert (stats["trades"], stats["wins"], stats["losses"], stats["breakeven"]) == (8, 4, 3, 1)
    assert stats["win_rate"] == "0.5000"
    assert (stats["gross_profit"], stats["gross_loss"], stats["net_profit"]) == (
        "360.00", "-480.00", "-120.00",
    )  # fmt: skip
    assert (stats["profit_factor"], stats["expectancy"]) == ("0.7500", "-15.00")
    assert (stats["average_win"], stats["average_loss"]) == ("90.00", "-160.00")
    assert stats["longest_loss_streak"] == {"count": 2, "amount": "-80.00"}
    assert stats["average_holding_seconds"] == 3600
    deepest = body["max_drawdown"]
    assert (deepest["amount"], deepest["percent"]) == ("400.00", "0.3279")  # 400 / 1220
    assert (deepest["peak"], deepest["trough"]) == ("1220.00", "820.00")
    assert deepest["peak_time"] == "2026-03-06T12:00:00Z"
    assert deepest["recovered_time"] is None
    assert body["absolute_drawdown"] == "180.00"
    assert body["recovery_factor"] == "-0.3000"


def test_summary_for_a_period_starts_from_the_balance_at_that_moment(
    client, account_and_key, seeded
) -> None:
    # From trade 5 on. Before that: 1000 + 100 - 50 - 30 + 200 = 1220.
    body = client.get(
        url(account_and_key[0], "/summary"),
        params={"closed_from": "2026-03-07T12:00:00Z"},
        headers=seeded,
    ).json()

    assert body["starting_balance"] == "1220.00"
    assert body["ending_balance"] == "880.00"
    assert body["stats"]["trades"] == 4 and body["stats"]["net_profit"] == "-340.00"
    assert body["max_drawdown"]["peak"] == "1220.00"
    assert body["max_drawdown"]["peak_time"] is None  # the peak is the period's opening balance
    assert body["closed_from"] == "2026-03-07T12:00:00Z"


def test_summary_period_end_is_exclusive_and_offsets_are_understood(
    client, account_and_key, seeded
) -> None:
    # 14:00+02:00 on 6 March is 12:00 UTC: trade 4 closes exactly then and is left out.
    body = client.get(
        url(account_and_key[0], "/summary"),
        params={"closed_until": "2026-03-06T14:00:00+02:00"},
        headers=seeded,
    ).json()
    assert body["stats"]["trades"] == 3 and body["ending_balance"] == "1020.00"


def test_summary_of_an_empty_period(client, account_and_key, seeded) -> None:
    body = client.get(
        url(account_and_key[0], "/summary"),
        params={"closed_from": "2030-01-01T00:00:00Z"},
        headers=seeded,
    ).json()
    assert body["stats"]["trades"] == 0 and body["stats"]["win_rate"] is None
    assert body["starting_balance"] == body["ending_balance"] == "880.00"
    assert body["max_drawdown"] is None


def test_equity_curve(client, account_and_key, seeded) -> None:
    body = client.get(url(account_and_key[0], "/equity-curve"), headers=seeded).json()

    assert body["starting_balance"] == "1000.00" and body["currency"] == "USD"
    points = body["points"]
    assert [p["balance"] for p in points] == [
        "1100.00", "1050.00", "1020.00", "1220.00", "820.00", "870.00", "870.00", "880.00",
    ]  # fmt: skip
    assert [p["drawdown"] for p in points][4] == "400.00"
    assert points[4]["drawdown_pct"] == "0.3279"
    assert points[0]["time"] == "2026-03-03T12:00:00Z" and points[0]["ticket"] == 1


@pytest.mark.parametrize(
    "params",
    [
        {"closed_from": "2026-03-07T12:00:00"},  # no timezone
        {"closed_until": "2026-03-07"},
        {"closed_from": "yesterday"},
        {"closed_from": "2026-03-07T12:00:00Z", "closed_until": "2026-03-07T12:00:00Z"},
        {"closed_from": "2026-03-08T12:00:00Z", "closed_until": "2026-03-07T12:00:00Z"},
    ],
)
def test_bad_periods_are_rejected(client, account_and_key, seeded, params) -> None:
    assert (
        client.get(url(account_and_key[0], "/summary"), params=params, headers=seeded).status_code
        == 422
    )


# --- breakdowns ---------------------------------------------------------------------------


def groups_of(client, account, headers, **params) -> dict[str, dict]:
    response = client.get(url(account, "/breakdown"), params=params, headers=headers)
    assert response.status_code == 200, response.text
    return {g["key"]: g["stats"] for g in response.json()["groups"]}


def test_breakdown_by_instrument_uses_common_names_best_first(
    client, account_and_key, seeded
) -> None:
    body = client.get(
        url(account_and_key[0], "/breakdown"), params={"by": "instrument"}, headers=seeded
    ).json()

    assert body["timezone"] is None
    assert [(g["key"], g["stats"]["net_profit"]) for g in body["groups"]] == [
        ("NAS100", "220.00"),
        ("XAUUSD", "-340.00"),
    ]


def test_breakdown_by_weekday_on_a_chosen_clock(client, account_and_key, seeded) -> None:
    groups = groups_of(client, account_and_key[0], seeded, by="weekday", tz="UTC")

    assert list(groups) == [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    ]  # fmt: skip
    assert (groups["Tuesday"]["trades"], groups["Tuesday"]["net_profit"]) == (2, "110.00")
    assert groups["Saturday"]["net_profit"] == "-400.00"
    assert groups["Monday"]["trades"] == 1


def test_breakdown_by_hour(client, account_and_key, seeded) -> None:
    groups = groups_of(client, account_and_key[0], seeded, by="hour", tz="UTC")
    assert len(groups) == 24 and groups["11"]["trades"] == 8  # every trade opened 11:00 UTC


def test_breakdown_by_session_follows_new_york_daylight_saving(
    client, account_and_key, seeded
) -> None:
    # 11:00 UTC is 06:00 in New York until 7 March (London session), then 07:00 from the
    # clocks changing on 8 March (New York AM). Default clock is America/New_York.
    groups = groups_of(client, account_and_key[0], seeded, by="session")
    assert (groups["London"]["trades"], groups["London"]["net_profit"]) == (5, "-180.00")
    assert (groups["New York AM"]["trades"], groups["New York AM"]["net_profit"]) == (3, "60.00")


@pytest.mark.parametrize(
    "params",
    [{}, {"by": "colour"}, {"by": "hour", "tz": "Mars/Olympus"}, {"by": "hour", "tz": "../etc"}],
)
def test_bad_breakdown_requests_are_rejected(client, account_and_key, seeded, params) -> None:
    response = client.get(url(account_and_key[0], "/breakdown"), params=params, headers=seeded)
    assert response.status_code == 422


# --- trades --------------------------------------------------------------------------------


def tickets(client, account, headers, **params) -> list[int]:
    response = client.get(url(account, "/trades"), params=params, headers=headers)
    assert response.status_code == 200, response.text
    return [t["ticket"] for t in response.json()["items"]]


def test_trades_come_newest_first_with_paging(client, account_and_key, seeded) -> None:
    account = account_and_key[0]
    page = client.get(url(account, "/trades"), params={"limit": 3}, headers=seeded).json()

    assert (page["total"], page["limit"], page["offset"]) == (8, 3, 0)
    assert [t["ticket"] for t in page["items"]] == [8, 7, 6]
    assert tickets(client, account, seeded, limit=3, offset=3) == [5, 4, 3]
    assert tickets(client, account, seeded, limit=3, offset=6) == [2, 1]
    assert tickets(client, account, seeded, limit=3, offset=60) == []
    assert tickets(client, account, seeded, order="asc", limit=2) == [1, 2]


def test_a_trade_shows_both_symbol_names_and_the_net_result(
    client, account_and_key, seeded
) -> None:
    items = client.get(
        url(account_and_key[0], "/trades"), params={"order": "asc", "limit": 1}, headers=seeded
    ).json()["items"]
    assert items == [
        {
            "ticket": 1,
            "symbol": "T100.IFX_M",
            "instrument": "NAS100",
            "direction": "buy",
            "volume": "0.1000",
            "open_time": "2026-03-03T11:00:00Z",
            "close_time": "2026-03-03T12:00:00Z",
            "open_price": "100.00000",
            "close_price": "101.00000",
            "sl": None,
            "tp": None,
            "commission": "0.00",
            "swap": "0.00",
            "profit": "100.00",
            "net": "100.00",
            "strategy_tag": None,
        }
    ]


def test_trades_can_be_sorted_by_result(client, account_and_key, seeded) -> None:
    account = account_and_key[0]
    assert tickets(client, account, seeded, sort="net", order="asc") == [5, 2, 3, 7, 8, 6, 1, 4]
    assert tickets(client, account, seeded, sort="profit", order="desc", limit=2) == [4, 1]
    assert tickets(client, account, seeded, sort="open_time", order="asc", limit=2) == [1, 2]


def test_trades_can_be_filtered(client, account_and_key, seeded) -> None:
    account = account_and_key[0]
    assert sorted(tickets(client, account, seeded, symbol="NAS100")) == [1, 2, 3, 4]
    assert sorted(tickets(client, account, seeded, symbol="nas100")) == [1, 2, 3, 4]
    assert sorted(tickets(client, account, seeded, symbol="T100.IFX_M")) == [1, 2, 3, 4]
    assert sorted(tickets(client, account, seeded, symbol="XAUUSD")) == [5, 6, 7, 8]
    assert tickets(client, account, seeded, symbol="GER40") == []
    assert sorted(tickets(client, account, seeded, direction="sell")) == [5, 6, 7, 8]
    assert sorted(tickets(client, account, seeded, result="loss")) == [2, 3, 5]
    assert sorted(tickets(client, account, seeded, result="win")) == [1, 4, 6, 8]
    assert tickets(client, account, seeded, result="breakeven") == [7]
    assert sorted(
        tickets(client, account, seeded, result="loss", symbol="NAS100", direction="buy")
    ) == [2, 3]


def test_the_total_counts_the_filtered_trades_not_just_the_page(
    client, account_and_key, seeded
) -> None:
    page = client.get(
        url(account_and_key[0], "/trades"),
        params={"result": "win", "limit": 1, "closed_from": "2026-03-07T12:00:00Z"},
        headers=seeded,
    ).json()
    assert page["total"] == 2 and [t["ticket"] for t in page["items"]] == [8]  # wins 6 and 8


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"sort": "volume"}, {"order": "up"},
     {"direction": "long"}, {"result": "draw"}],
)  # fmt: skip
def test_bad_trade_queries_are_rejected(client, account_and_key, seeded, params) -> None:
    response = client.get(url(account_and_key[0], "/trades"), params=params, headers=seeded)
    assert response.status_code == 422


def test_sorting_by_net_counts_commission_and_swap(
    client, db_session, account_and_key, user_headers
):
    account = account_and_key[0]
    base = {
        "symbol": "EURUSD", "direction": "buy", "volume": "1",
        "open_time": "2026-03-03T10:00:00+00:00", "close_time": "2026-03-03T11:00:00+00:00",
        "open_price": "1.1", "close_price": "1.2",
    }  # fmt: skip
    costly = TradeIn.model_validate(base | {"ticket": 1, "profit": "50", "commission": "-60"})
    cheap = TradeIn.model_validate(base | {"ticket": 2, "profit": "20", "swap": "1"})
    ingest_trades(db_session, account, [costly, cheap])  # nets: -10 and 21

    assert tickets(client, account, user_headers, sort="net", order="asc") == [1, 2]
    assert tickets(client, account, user_headers, sort="profit", order="asc") == [2, 1]
    assert tickets(client, account, user_headers, result="loss") == [1]  # a loss despite +50 profit
