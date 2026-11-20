from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Account, ApiKey, User
from app.security import generate_api_key, hash_api_key
from app.services.users import find_user_by_email
from app.timezones import validate_server_time_rule

MAX_ACTIVE_KEYS_PER_ACCOUNT = 10


class DuplicateAccountLabel(Exception):
    """The user already has an account with this label."""


class TooManyKeys(Exception):
    """The account already has the maximum number of active API keys."""


class EmailTaken(Exception):
    """Another user already has this email."""


def issue_api_key(db: Session, account: Account, label: str | None = None) -> tuple[ApiKey, str]:
    """Issue a new key for an account. Returns the stored row and the plaintext (shown once)."""
    key, prefix, key_hash = generate_api_key()
    row = ApiKey(account_id=account.id, key_prefix=prefix, key_hash=key_hash, label=label)
    db.add(row)
    db.commit()
    return row, key


def create_api_key(db: Session, account: Account) -> str:
    """Issue a new key for an account and return the plaintext (shown once)."""
    return issue_api_key(db, account)[1]


def issue_api_key_checked(
    db: Session, account: Account, label: str | None = None
) -> tuple[ApiKey, str]:
    """Like issue_api_key, but refuses once the account has too many active keys."""
    active = db.scalar(
        select(func.count(ApiKey.id)).where(
            ApiKey.account_id == account.id, ApiKey.revoked_at.is_(None)
        )
    )
    if (active or 0) >= MAX_ACTIVE_KEYS_PER_ACCOUNT:
        raise TooManyKeys(
            f"an account can have at most {MAX_ACTIVE_KEYS_PER_ACCOUNT} active keys; "
            "revoke one first"
        )
    return issue_api_key(db, account, label)


def list_api_keys(db: Session, account: Account) -> list[ApiKey]:
    """All keys of the account, newest first (the plaintext is never stored)."""
    return list(
        db.scalars(select(ApiKey).where(ApiKey.account_id == account.id).order_by(ApiKey.id.desc()))
    )


def revoke_api_key_by_id(db: Session, account: Account, key_id: int) -> ApiKey | None:
    """Revoke one key of this account. None if the account has no such key.

    Safe to repeat: an already revoked key keeps its original revocation time."""
    key = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.account_id == account.id))
    if key is None:
        return None
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        db.commit()
    return key


def _label_taken(db: Session, user_id: int, label: str, except_id: int | None = None) -> bool:
    query = select(Account.id).where(
        Account.user_id == user_id, func.lower(Account.label) == label.lower()
    )
    if except_id is not None:
        query = query.where(Account.id != except_id)
    return db.scalar(query) is not None


def add_account(
    db: Session,
    user: User,
    *,
    label: str,
    broker: str | None = None,
    currency: str = "USD",
    starting_balance: Decimal = Decimal("0"),
    is_demo: bool = False,
    server_timezone: str | None = None,
) -> Account:
    """Create an account for an existing user (no API key; issue one separately).

    Raises DuplicateAccountLabel or InvalidServerTimeRule."""
    rule = validate_server_time_rule(server_timezone) if server_timezone else None
    if _label_taken(db, user.id, label):
        raise DuplicateAccountLabel(f"you already have an account called {label!r}")
    account = Account(
        user_id=user.id,
        label=label,
        broker=broker,
        currency=currency.upper(),
        starting_balance=starting_balance,
        is_demo=is_demo,
        server_timezone=rule,
    )
    db.add(account)
    try:
        db.commit()
    except IntegrityError as exc:  # two requests with the same label at the same moment
        db.rollback()
        raise DuplicateAccountLabel(f"you already have an account called {label!r}") from exc
    return account


def create_account(
    db: Session,
    *,
    email: str,
    label: str,
    broker: str | None = None,
    currency: str = "USD",
    starting_balance: Decimal = Decimal("0"),
    is_demo: bool = False,
    server_timezone: str | None = None,
) -> tuple[Account, str]:
    """Create (or reuse) the user, create the account, and issue its first API key."""
    user = find_user_by_email(db, email)
    if user is None:
        user = User(email=email.strip())
        db.add(user)
        db.flush()

    account = add_account(
        db,
        user,
        label=label,
        broker=broker,
        currency=currency,
        starting_balance=starting_balance,
        is_demo=is_demo,
        server_timezone=server_timezone,
    )
    return account, create_api_key(db, account)


def change_account(db: Session, account: Account, changes: dict[str, object]) -> Account:
    """Apply the given changes (field name -> new value) to an account owned by its caller.

    Raises DuplicateAccountLabel or InvalidServerTimeRule; nothing is saved in that case."""
    if "server_timezone" in changes:
        changes = {
            **changes,
            "server_timezone": validate_server_time_rule(str(changes["server_timezone"])),
        }
    if "currency" in changes:
        changes = {**changes, "currency": str(changes["currency"]).upper()}
    if "label" in changes and _label_taken(db, account.user_id, str(changes["label"]), account.id):
        raise DuplicateAccountLabel(f"you already have an account called {changes['label']!r}")
    for field, value in changes.items():
        setattr(account, field, value)
    db.commit()
    return account


def revoke_api_key(db: Session, key_prefix: str) -> int:
    """Revoke all active keys with this display prefix. Returns how many were revoked."""
    keys = db.scalars(
        select(ApiKey).where(ApiKey.key_prefix == key_prefix, ApiKey.revoked_at.is_(None))
    ).all()
    for key in keys:
        key.revoked_at = datetime.now(UTC)
    db.commit()
    return len(keys)


def find_account_by_api_key(db: Session, key: str) -> Account | None:
    """Return the account owning an active (non-revoked) key, else None."""
    return db.scalar(
        select(Account)
        .join(ApiKey, ApiKey.account_id == Account.id)
        .where(ApiKey.key_hash == hash_api_key(key), ApiKey.revoked_at.is_(None))
    )


def update_account(
    db: Session,
    account_id: int,
    *,
    server_timezone: str | None = None,
    currency: str | None = None,
    starting_balance: Decimal | None = None,
) -> Account | None:
    """Change the given settings on an account (None = leave as is). None if not found."""
    account = db.get(Account, account_id)
    if account is None:
        return None
    changes: dict[str, object] = {}
    if server_timezone is not None:
        changes["server_timezone"] = server_timezone
    if currency is not None:
        changes["currency"] = currency
    if starting_balance is not None:
        changes["starting_balance"] = starting_balance
    return change_account(db, account, changes)


def change_email(db: Session, email: str, new_email: str) -> User | None:
    """Give a user a new login email. None if there is no user with the old one.

    Raises EmailTaken if somebody else already uses the new one."""
    user = find_user_by_email(db, email)
    if user is None:
        return None
    other = find_user_by_email(db, new_email)
    if other is not None and other.id != user.id:
        raise EmailTaken(f"{new_email} already belongs to another user")
    user.email = new_email.strip()
    db.commit()
    return user
