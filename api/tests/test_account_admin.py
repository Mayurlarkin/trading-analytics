"""Creating accounts, managing API keys and importing reports with a login (Phase 3b).

The things that matter most: nobody can touch another user's account or keys, a login and an
API key are never interchangeable, and a revoked key stops working at once."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.cli import main as cli_main
from app.models import Account, ApiKey, Trade, User
from app.services.accounts import MAX_ACTIVE_KEYS_PER_ACCOUNT, create_account
from tests.mt5_builder import build_report

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NEW_ACCOUNT = {"label": "IFX Demo", "broker": "IFX", "currency": "zar", "is_demo": True}


@pytest.fixture
def other_user(db_session, login_headers):
    """A second person with an account and a key of their own."""
    account, key = create_account(db_session, email="other@example.com", label="Theirs")
    return {"account": account, "key": key, "headers": login_headers("other@example.com")}


def make_account(client, headers, **overrides) -> dict:
    response = client.post("/accounts", json={**NEW_ACCOUNT, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --- creating accounts ----------------------------------------------------------------


def test_create_an_account(client, user_headers) -> None:
    body = make_account(
        client, user_headers, starting_balance="100000.50", server_timezone="ny_close"
    )
    assert body["label"] == "IFX Demo"
    assert body["currency"] == "ZAR"  # stored in capitals
    assert Decimal(body["starting_balance"]) == Decimal("100000.50")
    assert body["server_timezone"] == "ny_close"
    assert (body["trade_count"], body["last_close_time"]) == (0, None)

    listed = client.get("/accounts", headers=user_headers).json()
    assert [a["label"] for a in listed] == ["Test", "IFX Demo"]


def test_a_new_account_belongs_to_the_caller_and_has_no_key(
    client, db_session, user_headers, account_and_key
) -> None:
    body = make_account(client, user_headers)
    account = db_session.get(Account, body["id"])
    assert account.user_id == account_and_key[0].user_id
    assert client.get(f"/accounts/{body['id']}/api-keys", headers=user_headers).json() == []


def test_you_cannot_create_an_account_for_somebody_else(client, user_headers, other_user) -> None:
    response = client.post(
        "/accounts",
        json={**NEW_ACCOUNT, "user_id": other_user["account"].user_id},
        headers=user_headers,
    )
    assert response.status_code == 422  # unknown fields are refused, not ignored


@pytest.mark.parametrize(
    "bad",
    [
        {"label": ""},
        {"label": "  "},
        {"label": "x" * 101},
        {"currency": "RAND"},
        {"currency": "R1"},
        {"starting_balance": "-1"},
        {"starting_balance": "10.123"},
        {"server_timezone": "Mars/Olympus"},
    ],
)
def test_invalid_accounts_are_refused(client, user_headers, bad) -> None:
    response = client.post("/accounts", json={**NEW_ACCOUNT, **bad}, headers=user_headers)
    assert response.status_code == 422, bad


def test_label_must_be_unique_per_person_not_across_people(
    client, user_headers, other_user
) -> None:
    make_account(client, user_headers)
    assert client.post("/accounts", json=NEW_ACCOUNT, headers=user_headers).status_code == 409
    shouted = {**NEW_ACCOUNT, "label": "ifx demo"}
    assert client.post("/accounts", json=shouted, headers=user_headers).status_code == 409
    # Somebody else may use the same name.
    assert (
        client.post("/accounts", json=NEW_ACCOUNT, headers=other_user["headers"]).status_code == 201
    )


def test_account_management_needs_a_login_not_an_api_key(
    client, auth_headers, account_and_key
) -> None:
    account_id = account_and_key[0].id
    calls = [
        ("post", "/accounts", {"json": NEW_ACCOUNT}),
        ("patch", f"/accounts/{account_id}", {"json": {"label": "x"}}),
        ("get", f"/accounts/{account_id}/api-keys", {}),
        ("post", f"/accounts/{account_id}/api-keys", {}),
        ("delete", f"/accounts/{account_id}/api-keys/1", {}),
        (
            "post",
            f"/accounts/{account_id}/import/mt5-report",
            {"files": {"file": ("r.xlsx", build_report(), XLSX)}},
        ),
    ]
    for method, path, kwargs in calls:
        for headers in ({}, auth_headers):  # nothing at all, and the machine credential
            response = getattr(client, method)(path, headers=headers, **kwargs)
            assert response.status_code == 401, (method, path, headers)


# --- changing accounts ----------------------------------------------------------------


def test_patch_changes_only_what_was_sent(client, user_headers) -> None:
    account = make_account(client, user_headers, broker="IFX", server_timezone="ny_close")
    response = client.patch(
        f"/accounts/{account['id']}",
        json={"starting_balance": "5000", "currency": "usd"},
        headers=user_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["currency"], Decimal(body["starting_balance"])) == ("USD", Decimal("5000"))
    assert (body["label"], body["broker"], body["server_timezone"]) == (
        "IFX Demo",
        "IFX",
        "ny_close",
    )
    assert body["is_demo"] is True


def test_patch_can_clear_the_broker_but_not_required_fields(client, user_headers) -> None:
    account = make_account(client, user_headers, broker="IFX")
    path = f"/accounts/{account['id']}"
    assert client.patch(path, json={"broker": None}, headers=user_headers).json()["broker"] is None
    for field in ("label", "currency", "starting_balance", "is_demo", "server_timezone"):
        response = client.patch(path, json={field: None}, headers=user_headers)
        assert response.status_code == 422, field


def test_patch_with_nothing_to_change_or_unknown_fields_is_refused(client, user_headers) -> None:
    path = f"/accounts/{make_account(client, user_headers)['id']}"
    assert client.patch(path, json={}, headers=user_headers).status_code == 422
    assert client.patch(path, json={"user_id": 1}, headers=user_headers).status_code == 422
    assert client.patch(path, json={"id": 99}, headers=user_headers).status_code == 422
    # A valid change with something extra is refused as a whole, not half applied.
    mixed = {"label": "Renamed", "user_id": 1}
    assert client.patch(path, json=mixed, headers=user_headers).status_code == 422
    assert client.get(path, headers=user_headers).json()["label"] == "IFX Demo"


def test_a_failed_patch_changes_nothing(client, user_headers) -> None:
    make_account(client, user_headers, label="Other one")
    account = make_account(client, user_headers, server_timezone="ny_close")
    path = f"/accounts/{account['id']}"
    bad = {"label": "other ONE", "starting_balance": "999"}
    assert client.patch(path, json=bad, headers=user_headers).status_code == 409
    bad_zone = {"starting_balance": "999", "server_timezone": "Mars/Olympus"}
    assert client.patch(path, json=bad_zone, headers=user_headers).status_code == 422
    after = client.get(path, headers=user_headers).json()
    assert Decimal(after["starting_balance"]) == 0
    assert after["server_timezone"] == "ny_close"


def test_renaming_an_account_to_itself_in_another_case_is_fine(client, user_headers) -> None:
    account = make_account(client, user_headers)
    response = client.patch(
        f"/accounts/{account['id']}", json={"label": "ifx DEMO"}, headers=user_headers
    )
    assert response.status_code == 200
    assert response.json()["label"] == "ifx DEMO"


def test_a_new_starting_balance_changes_the_analytics(
    client, user_headers, db_session, account_and_key, trade_payload, auth_headers
) -> None:
    account = account_and_key[0]
    client.post(
        "/ingest/trades", json={"trades": [trade_payload(profit="100.00")]}, headers=auth_headers
    )
    path = f"/accounts/{account.id}"
    before = client.get(f"{path}/equity-curve", headers=user_headers).json()
    client.patch(path, json={"starting_balance": "1000"}, headers=user_headers)
    after = client.get(f"{path}/equity-curve", headers=user_headers).json()
    assert before["points"][-1]["balance"] != after["points"][-1]["balance"]
    assert Decimal(after["points"][-1]["balance"]) == Decimal("1096.50")  # 1000 + 100 - 3.50


def test_nobody_can_change_another_persons_account(client, user_headers, other_user) -> None:
    theirs = f"/accounts/{other_user['account'].id}"
    response = client.patch(theirs, json={"label": "mine now"}, headers=user_headers)
    assert response.status_code == 404
    assert client.get(theirs, headers=other_user["headers"]).json()["label"] == "Theirs"
    # ...and a missing account looks exactly the same.
    missing = client.patch("/accounts/999999", json={"label": "x"}, headers=user_headers)
    assert missing.status_code == 404
    assert missing.json() == response.json()


# --- API keys -------------------------------------------------------------------------


def test_a_new_key_works_once_issued_and_is_never_shown_again(
    client, db_session, user_headers, trade_payload
) -> None:
    account = make_account(client, user_headers)
    created = client.post(
        f"/accounts/{account['id']}/api-keys", json={"label": "MT5 EA"}, headers=user_headers
    )
    assert created.status_code == 201
    secret = created.json()["key"]
    assert secret.startswith("ta_")
    assert created.json()["prefix"] == secret[: len(created.json()["prefix"])]
    assert created.json()["label"] == "MT5 EA"

    sent = client.post(
        "/ingest/trades", json={"trades": [trade_payload()]}, headers={"X-API-Key": secret}
    )
    assert sent.status_code == 200, sent.text
    assert db_session.scalars(select(Trade).where(Trade.account_id == account["id"])).one()

    listing = client.get(f"/accounts/{account['id']}/api-keys", headers=user_headers)
    assert listing.status_code == 200
    (only,) = listing.json()
    assert only["label"] == "MT5 EA"
    assert set(only) == {"id", "prefix", "label", "created_at", "revoked_at"}
    assert secret not in listing.text
    stored = db_session.scalars(select(ApiKey).where(ApiKey.id == only["id"])).one()
    assert secret not in (stored.key_hash, stored.key_prefix)
    assert stored.key_hash not in listing.text


def test_issuing_a_key_needs_no_body_and_validates_the_label(client, user_headers) -> None:
    path = f"/accounts/{make_account(client, user_headers)['id']}/api-keys"
    plain = client.post(path, headers=user_headers)
    assert plain.status_code == 201 and plain.json()["label"] is None
    assert client.post(path, json={"label": "x" * 65}, headers=user_headers).status_code == 422
    assert client.post(path, json={"nope": 1}, headers=user_headers).status_code == 422


def test_revoking_a_key_stops_it_immediately_and_only_that_key(
    client, user_headers, trade_payload
) -> None:
    account_id = make_account(client, user_headers)["id"]
    path = f"/accounts/{account_id}/api-keys"
    first = client.post(path, headers=user_headers).json()
    second = client.post(path, headers=user_headers).json()

    def ingest(secret: str) -> int:
        return client.post(
            "/ingest/trades", json={"trades": [trade_payload()]}, headers={"X-API-Key": secret}
        ).status_code

    assert client.delete(f"{path}/{first['id']}", headers=user_headers).status_code == 204
    assert ingest(first["key"]) == 401
    assert ingest(second["key"]) == 200

    listed = {k["id"]: k for k in client.get(path, headers=user_headers).json()}
    assert listed[first["id"]]["revoked_at"] is not None
    assert listed[second["id"]]["revoked_at"] is None
    assert list(listed) == [second["id"], first["id"]]  # newest first


def test_revoking_twice_is_harmless_and_keeps_the_first_time(client, user_headers) -> None:
    account_id = make_account(client, user_headers)["id"]
    path = f"/accounts/{account_id}/api-keys"
    key = client.post(path, headers=user_headers).json()
    client.delete(f"{path}/{key['id']}", headers=user_headers)
    first_time = client.get(path, headers=user_headers).json()[0]["revoked_at"]
    assert client.delete(f"{path}/{key['id']}", headers=user_headers).status_code == 204
    assert client.get(path, headers=user_headers).json()[0]["revoked_at"] == first_time


def test_an_unknown_key_id_is_a_404(client, user_headers) -> None:
    path = f"/accounts/{make_account(client, user_headers)['id']}/api-keys"
    assert client.delete(f"{path}/999999", headers=user_headers).status_code == 404


def test_an_account_can_only_have_a_limited_number_of_active_keys(client, user_headers) -> None:
    path = f"/accounts/{make_account(client, user_headers)['id']}/api-keys"
    ids = [
        client.post(path, headers=user_headers).json()["id"]
        for _ in range(MAX_ACTIVE_KEYS_PER_ACCOUNT)
    ]
    assert client.post(path, headers=user_headers).status_code == 409
    client.delete(f"{path}/{ids[0]}", headers=user_headers)  # revoked keys do not count
    assert client.post(path, headers=user_headers).status_code == 201
    assert client.post(path, headers=user_headers).status_code == 409


def test_nobody_can_list_issue_or_revoke_keys_on_another_persons_account(
    client, db_session, user_headers, other_user, trade_payload
) -> None:
    theirs = f"/accounts/{other_user['account'].id}/api-keys"
    their_key_id = (
        db_session.scalars(select(ApiKey).where(ApiKey.account_id == other_user["account"].id))
        .one()
        .id
    )

    assert client.get(theirs, headers=user_headers).status_code == 404
    assert client.post(theirs, headers=user_headers).status_code == 404
    assert client.delete(f"{theirs}/{their_key_id}", headers=user_headers).status_code == 404

    # Their key still works, and they still have exactly one key.
    db_session.rollback()
    ingest = client.post(
        "/ingest/trades",
        json={"trades": [trade_payload()]},
        headers={"X-API-Key": other_user["key"]},
    )
    assert ingest.status_code == 200
    assert len(client.get(theirs, headers=other_user["headers"]).json()) == 1


def test_a_key_id_from_another_account_cannot_be_revoked_through_your_own(
    client, db_session, user_headers, other_user, trade_payload
) -> None:
    mine = f"/accounts/{make_account(client, user_headers)['id']}/api-keys"
    their_key_id = (
        db_session.scalars(select(ApiKey).where(ApiKey.account_id == other_user["account"].id))
        .one()
        .id
    )
    assert client.delete(f"{mine}/{their_key_id}", headers=user_headers).status_code == 404
    db_session.rollback()
    ingest = client.post(
        "/ingest/trades",
        json={"trades": [trade_payload()]},
        headers={"X-API-Key": other_user["key"]},
    )
    assert ingest.status_code == 200


# --- importing a report with a login --------------------------------------------------


def upload(client, headers, account_id, data=None, **params):
    files = {"file": ("report.xlsx", build_report() if data is None else data, XLSX)}
    return client.post(
        f"/accounts/{account_id}/import/mt5-report", params=params, files=files, headers=headers
    )


def test_a_report_can_be_imported_with_a_login(client, user_headers, account_and_key) -> None:
    account = account_and_key[0]
    refused = upload(client, user_headers, account.id)
    assert refused.status_code == 422 and "server time" in refused.json()["detail"]

    client.patch(
        f"/accounts/{account.id}", json={"server_timezone": "ny_close"}, headers=user_headers
    )
    first = upload(client, user_headers, account.id)
    assert first.status_code == 200, first.text
    assert first.json()["created"] == first.json()["positions_in_report"] > 0

    again = upload(client, user_headers, account.id)
    assert (again.json()["created"], again.json()["unchanged"]) == (0, first.json()["created"])

    summary = client.get(f"/accounts/{account.id}/summary", headers=user_headers).json()
    assert summary["stats"]["trades"] == first.json()["created"]


def test_both_import_routes_give_the_same_answer(
    client, db_session, user_headers, auth_headers, account_and_key
) -> None:
    account = account_and_key[0]
    by_login = upload(client, user_headers, account.id, server_time="ny_close", dry_run="true")
    by_key = client.post(
        "/import/mt5-report",
        params={"server_time": "ny_close", "dry_run": "true"},
        files={"file": ("report.xlsx", build_report(), XLSX)},
        headers=auth_headers,
    )
    assert by_login.status_code == by_key.status_code == 200
    assert by_login.json() == by_key.json()
    assert by_login.json()["dry_run"] is True
    assert db_session.scalars(select(Trade)).first() is None


def test_login_import_errors_match_the_key_import(client, user_headers, account_and_key) -> None:
    account_id = account_and_key[0].id
    assert (
        upload(
            client, user_headers, account_id, b"not a spreadsheet", server_time="ny_close"
        ).status_code
        == 400
    )
    assert upload(client, user_headers, account_id, server_time="Mars/Olympus").status_code == 422
    too_big = b"x" * (10 * 1024 * 1024 + 1)
    assert (
        upload(client, user_headers, account_id, too_big, server_time="ny_close").status_code == 413
    )


def test_nobody_can_import_into_another_persons_account(
    client, db_session, user_headers, other_user
) -> None:
    response = upload(client, user_headers, other_user["account"].id, server_time="ny_close")
    assert response.status_code == 404
    db_session.rollback()
    assert db_session.scalars(select(Trade)).first() is None


# --- the whole story, end to end ------------------------------------------------------


def test_new_person_flow_account_key_ingest_then_read(
    client, db_session, login_headers, trade_payload
) -> None:
    create_account(db_session, email="fresh@example.com", label="Seed")  # the CLI's first step
    headers = login_headers("fresh@example.com")
    account = make_account(client, headers, label="Live", starting_balance="1000")
    key = client.post(f"/accounts/{account['id']}/api-keys", headers=headers).json()["key"]

    sent = client.post(
        "/ingest/trades",
        json={"trades": [trade_payload(profit="50.00", commission="0")]},
        headers={"X-API-Key": key},
    )
    assert sent.status_code == 200
    summary = client.get(f"/accounts/{account['id']}/summary", headers=headers).json()
    assert summary["stats"]["trades"] == 1
    assert Decimal(summary["stats"]["net_profit"]) == Decimal("50.00")
    assert Decimal(summary["ending_balance"]) == Decimal("1050.00")
    assert datetime.now(UTC)  # (keeps the import honest in case of future time assertions)


# --- command line: changing the login email -------------------------------------------


def test_cli_update_user_changes_the_login_email(engine, db_session, monkeypatch, capsys) -> None:
    monkeypatch.setattr("app.cli.get_engine", lambda: engine)
    create_account(db_session, email="old@example.com", label="A")
    assert (
        cli_main(["update-user", "--email", "OLD@example.com", "--new-email", "New@Example.com"])
        == 0
    )
    assert "Login email is now New@Example.com" in capsys.readouterr().out
    db_session.rollback()
    assert db_session.scalars(select(User.email)).one() == "New@Example.com"


def test_cli_update_user_refuses_a_taken_or_unknown_email(
    engine, db_session, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("app.cli.get_engine", lambda: engine)
    create_account(db_session, email="a@example.com", label="A")
    create_account(db_session, email="b@example.com", label="B")
    assert (
        cli_main(["update-user", "--email", "a@example.com", "--new-email", "B@example.com"]) == 1
    )
    assert "already belongs" in capsys.readouterr().err
    assert (
        cli_main(["update-user", "--email", "nobody@example.com", "--new-email", "c@example.com"])
        == 1
    )
    assert "No user" in capsys.readouterr().err
    # Changing only the capitals of your own address is allowed.
    assert (
        cli_main(["update-user", "--email", "a@example.com", "--new-email", "A@example.com"]) == 0
    )


def test_cli_create_account_refuses_a_duplicate_label(
    engine, db_session, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("app.cli.get_engine", lambda: engine)
    assert cli_main(["create-account", "--email", "a@example.com", "--label", "A", "--quiet"]) == 0
    capsys.readouterr()
    assert cli_main(["create-account", "--email", "A@example.com", "--label", "a", "--quiet"]) == 1
    assert "already have an account" in capsys.readouterr().err
    assert len(db_session.scalars(select(Account)).all()) == 1
