from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import DEV_JWT_SECRET
from app.models import User
from app.security import create_access_token
from app.services.accounts import create_account
from app.services.users import WeakPassword, authenticate, set_password
from tests.conftest import TEST_PASSWORD


def login(client: TestClient, email: str, password: str):
    return client.post("/auth/login", data={"username": email, "password": password})


@pytest.fixture
def user(db_session: Session, account_and_key) -> User:
    set_password(db_session, "trader@example.com", TEST_PASSWORD)
    return account_and_key[0].user


def test_login_returns_a_token_that_opens_me(client, user) -> None:
    response = login(client, "trader@example.com", TEST_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 8 * 3600
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json() == {"id": user.id, "email": "trader@example.com"}


def test_email_case_does_not_matter(client, user) -> None:
    assert login(client, "  Trader@Example.COM ", TEST_PASSWORD).status_code == 200


def test_wrong_password_and_unknown_email_look_exactly_the_same(client, user) -> None:
    wrong = login(client, "trader@example.com", "not-the-password")
    unknown = login(client, "nobody@example.com", TEST_PASSWORD)

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "incorrect email or password"}
    assert wrong.headers["www-authenticate"] == "Bearer"


def test_a_user_without_a_password_cannot_log_in(client, account_and_key) -> None:
    assert login(client, "trader@example.com", TEST_PASSWORD).status_code == 401
    assert login(client, "trader@example.com", "").status_code == 422  # the form needs a value


def test_an_enormous_password_is_refused_without_hashing_it(client, user) -> None:
    assert login(client, "trader@example.com", "x" * 100_000).status_code == 401


def test_protected_routes_need_a_token(client, user) -> None:
    for headers in ({}, {"Authorization": "Bearer nonsense"}, {"Authorization": "Basic abc"}):
        response = client.get("/auth/me", headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


def test_an_expired_token_is_refused(client, user) -> None:
    long_ago = datetime.now(UTC) - timedelta(days=1)
    token = create_access_token(user.id, DEV_JWT_SECRET, timedelta(hours=1), now=long_ago)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_a_token_for_a_user_who_no_longer_exists_is_refused(client, db_session, user) -> None:
    token = create_access_token(user.id, DEV_JWT_SECRET, timedelta(hours=1))
    db_session.execute(delete(User).where(User.id == user.id))
    db_session.commit()
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_an_api_key_is_not_a_login(client, user, auth_headers) -> None:
    assert client.get("/auth/me", headers=auth_headers).status_code == 401


def test_a_login_token_does_not_open_the_ingest_endpoint(client, user_headers) -> None:
    assert (
        client.post("/ingest/trades", json={"trades": []}, headers=user_headers).status_code == 401
    )


def test_password_rules_and_lookup(db_session: Session, account_and_key) -> None:
    with pytest.raises(WeakPassword):
        set_password(db_session, "trader@example.com", "short")
    with pytest.raises(WeakPassword):
        set_password(db_session, "trader@example.com", "x" * 129)
    assert set_password(db_session, "nobody@example.com", TEST_PASSWORD) is False
    assert authenticate(db_session, "trader@example.com", TEST_PASSWORD) is None  # none set yet
    assert set_password(db_session, "trader@example.com", TEST_PASSWORD)
    assert authenticate(db_session, "TRADER@example.com", TEST_PASSWORD) is not None


def test_each_user_gets_their_own_token(
    client, db_session, account_and_key, login_headers: Callable[[str], dict[str, str]]
) -> None:
    create_account(db_session, email="second@example.com", label="Other")
    first = client.get("/auth/me", headers=login_headers("trader@example.com")).json()
    second = client.get("/auth/me", headers=login_headers("second@example.com")).json()
    assert first["email"] == "trader@example.com" and second["email"] == "second@example.com"


def test_an_unknown_email_costs_as_much_time_as_a_wrong_password(
    client, db_session, user, account_and_key, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise the response time would reveal which emails have accounts."""
    spent = []
    monkeypatch.setattr("app.services.users.spend_password_time", lambda: spent.append(1))
    create_account(db_session, email="nopassword@example.com", label="No login")

    login(client, "nobody@example.com", TEST_PASSWORD)  # no such user
    login(client, "nopassword@example.com", TEST_PASSWORD)  # user without a password
    assert len(spent) == 2
    login(client, "trader@example.com", "wrong-password-here")  # real check, no decoy needed
    assert len(spent) == 2
