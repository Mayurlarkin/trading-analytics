import base64
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app import security
from app.config import DEV_JWT_SECRET, Settings
from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SECRET = DEV_JWT_SECRET
HOUR = timedelta(hours=1)


# --- passwords -------------------------------------------------------------------------


def test_a_password_checks_out_and_a_wrong_one_does_not() -> None:
    stored = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", stored)
    assert not verify_password("correct-horse-batterY", stored)
    assert not verify_password("", stored)


def test_every_hash_has_its_own_salt_and_the_password_is_not_in_it() -> None:
    first, second = hash_password("same-password"), hash_password("same-password")
    assert first != second
    assert "same-password" not in first
    assert first.startswith("scrypt$")


def test_the_cost_is_stored_in_the_hash_so_it_can_be_raised_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = hash_password("a-long-enough-password")
    monkeypatch.setattr(security, "SCRYPT_N", 2**5)
    new = hash_password("a-long-enough-password")

    assert verify_password("a-long-enough-password", old)  # still fine after the setting changed
    assert verify_password("a-long-enough-password", new)
    assert old.split("$")[1] == "16" and new.split("$")[1] == "32"


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "plain-text",
        "scrypt$16$8$1",
        "bcrypt$16$8$1$c2FsdA==$aGFzaA==",
        "scrypt$notanumber$8$1$c2FsdA==$aGFzaA==",
        "scrypt$16$8$1$!!!notbase64!!!$aGFzaA==",
        "scrypt$1$8$1$c2FsdA==$aGFzaA==",  # N must be a power of two above 1
    ],
)
def test_malformed_hashes_are_a_quiet_no(stored: str) -> None:
    assert verify_password("anything", stored) is False


def test_an_absurd_stored_cost_is_refused_instead_of_exhausting_memory() -> None:
    salt = base64.b64encode(b"0123456789abcdef").decode()
    assert verify_password("x", f"scrypt${2**30}$8$1${salt}${salt}") is False


# --- login tokens --------------------------------------------------------------------------


def test_a_fresh_token_gives_back_the_user() -> None:
    assert decode_access_token(create_access_token(42, SECRET, HOUR), SECRET) == 42


def test_an_expired_token_is_refused() -> None:
    long_ago = datetime.now(UTC) - 2 * HOUR
    assert decode_access_token(create_access_token(1, SECRET, HOUR, now=long_ago), SECRET) is None


def test_a_token_signed_with_another_secret_is_refused() -> None:
    forged = create_access_token(1, "another-secret-another-secret-another", HOUR)
    assert decode_access_token(forged, SECRET) is None


def test_an_unsigned_token_is_refused() -> None:
    claims = {"sub": "1", "exp": datetime.now(UTC) + HOUR}
    assert decode_access_token(jwt.encode(claims, key=None, algorithm="none"), SECRET) is None


def test_a_tampered_token_is_refused() -> None:
    header, payload, signature = create_access_token(1, SECRET, HOUR).split(".")
    other = create_access_token(2, SECRET, HOUR).split(".")[1]
    assert decode_access_token(f"{header}.{other}.{signature}", SECRET) is None
    assert decode_access_token(f"{header}.{payload}", SECRET) is None
    assert decode_access_token("not a token", SECRET) is None


def test_tokens_without_expiry_or_with_a_non_numeric_subject_are_refused() -> None:
    no_expiry = jwt.encode({"sub": "1"}, SECRET, algorithm="HS256")
    odd_subject = jwt.encode(
        {"sub": "abc", "exp": datetime.now(UTC) + HOUR}, SECRET, algorithm="HS256"
    )
    assert decode_access_token(no_expiry, SECRET) is None
    assert decode_access_token(odd_subject, SECRET) is None


# --- settings --------------------------------------------------------------------------


def test_development_may_use_the_built_in_secret_but_other_environments_may_not() -> None:
    assert Settings(_env_file=None).jwt_secret == DEV_JWT_SECRET
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, environment="production", jwt_secret="too-short")
    assert Settings(_env_file=None, environment="production", jwt_secret="x" * 40)


def test_an_empty_secret_counts_as_not_set() -> None:
    assert Settings(_env_file=None, jwt_secret="").jwt_secret == DEV_JWT_SECRET
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, environment="production", jwt_secret="")
