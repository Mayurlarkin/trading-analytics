from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli import main as cli_main
from app.models import Account, ApiKey, User
from app.schemas import TradeIn
from app.services.accounts import (
    create_account,
    create_api_key,
    find_account_by_api_key,
    revoke_api_key,
    update_account,
)
from app.services.ingest import ingest_trades


def test_create_account_stores_only_the_key_hash(db_session: Session) -> None:
    account, key = create_account(
        db_session,
        email="a@example.com",
        label="Main",
        currency="usd",
        starting_balance=Decimal("500"),
    )
    stored = db_session.scalars(select(ApiKey)).one()
    assert account.currency == "USD"
    assert account.starting_balance == Decimal("500")
    assert stored.key_hash != key
    assert key not in (stored.key_hash, stored.key_prefix)
    assert key.startswith(stored.key_prefix)


def test_second_account_reuses_the_user(db_session: Session) -> None:
    create_account(db_session, email="a@example.com", label="One")
    create_account(db_session, email="a@example.com", label="Two")
    assert db_session.scalar(select(func.count()).select_from(User)) == 1
    assert db_session.scalar(select(func.count()).select_from(Account)) == 2


def test_find_account_by_key_and_revocation(db_session: Session) -> None:
    account, key = create_account(db_session, email="a@example.com", label="Main")
    assert find_account_by_api_key(db_session, key).id == account.id
    assert find_account_by_api_key(db_session, "ta_wrong") is None

    prefix = db_session.scalars(select(ApiKey.key_prefix)).one()
    assert revoke_api_key(db_session, prefix) == 1
    assert find_account_by_api_key(db_session, key) is None
    assert revoke_api_key(db_session, prefix) == 0  # already revoked


def test_an_account_can_have_several_active_keys(db_session: Session) -> None:
    account, first = create_account(db_session, email="a@example.com", label="Main")
    second = create_api_key(db_session, account)
    assert first != second
    assert find_account_by_api_key(db_session, first).id == account.id
    assert find_account_by_api_key(db_session, second).id == account.id


def test_cli_create_account_prints_a_working_key(engine, db_session, monkeypatch, capsys) -> None:
    monkeypatch.setattr("app.cli.get_engine", lambda: engine)
    code = cli_main(["create-account", "--email", "cli@example.com", "--label", "CLI", "--quiet"])
    key = capsys.readouterr().out.strip()
    assert code == 0
    assert key.startswith("ta_")
    assert find_account_by_api_key(db_session, key) is not None


def test_cli_revoke_api_key(engine, db_session, monkeypatch, capsys) -> None:
    monkeypatch.setattr("app.cli.get_engine", lambda: engine)
    cli_main(["create-account", "--email", "cli@example.com", "--label", "CLI", "--quiet"])
    key = capsys.readouterr().out.strip()

    assert cli_main(["revoke-api-key", key[:11]]) == 0
    assert find_account_by_api_key(db_session, key) is None
    assert cli_main(["revoke-api-key", key[:11]]) == 1  # nothing left to revoke


def test_cli_create_account_with_server_time_and_update_account(
    engine, db_session, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("app.cli.get_engine", lambda: engine)
    assert (
        cli_main(
            [
                "create-account",
                "--email",
                "c@example.com",
                "--label",
                "C",
                "--server-time",
                "ny_close",
            ]
        )
        == 0
    )
    account = db_session.scalars(select(Account)).one()
    assert account.server_timezone == "ny_close"
    capsys.readouterr()

    code = cli_main(
        ["update-account", "--account-id", str(account.id), "--server-time", "Europe/Athens",
         "--currency", "zar", "--starting-balance", "100000"]
    )  # fmt: skip
    # End this session's read transaction first: MySQL (repeatable read) would otherwise keep
    # showing the snapshot from before the CLI's update. rollback() also expires the objects.
    db_session.rollback()
    account = db_session.scalars(select(Account)).one()
    assert code == 0
    assert (account.server_timezone, account.currency) == ("Europe/Athens", "ZAR")
    assert account.starting_balance == Decimal("100000")
    assert "server_time=Europe/Athens" in capsys.readouterr().out


def test_cli_rejects_a_bad_server_time_and_an_unknown_account(
    engine, db_session, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("app.cli.get_engine", lambda: engine)
    assert cli_main(["create-account", "--email", "c@example.com", "--label", "C", "--quiet"]) == 0
    account = db_session.scalars(select(Account)).one()
    capsys.readouterr()

    assert (
        cli_main(["update-account", "--account-id", str(account.id), "--server-time", "nope"]) == 2
    )
    assert "unknown server time rule" in capsys.readouterr().err
    assert cli_main(["update-account", "--account-id", "999999", "--currency", "USD"]) == 1


def test_cli_stats_prints_a_summary_and_handles_missing_and_empty_accounts(
    engine, db_session, monkeypatch, capsys, account_and_key, trade_payload
) -> None:
    monkeypatch.setattr("app.cli.get_engine", lambda: engine)
    account, _ = account_and_key
    assert cli_main(["stats", "--account-id", "999999"]) == 1
    assert "No account" in capsys.readouterr().err
    assert cli_main(["stats", "--account-id", str(account.id)]) == 0
    assert "no trades yet" in capsys.readouterr().out

    update_account(db_session, account.id, starting_balance=Decimal("1000"))
    for n, net in enumerate(["100", "-40"], start=1):
        ingest_trades(
            db_session,
            account,
            [TradeIn.model_validate(trade_payload(ticket=n, profit=net, commission="0"))],
        )
    assert cli_main(["stats", "--account-id", str(account.id), "--tz", "UTC"]) == 0
    out = capsys.readouterr().out

    assert "Net profit" in out and "60.00 USD (6.00% return)" in out
    assert "Profit factor" in out and "2.50" in out
    assert "Instrument" in out and "US30" in out
    assert "Session (UTC)" in out and "Weekday (UTC)" in out
