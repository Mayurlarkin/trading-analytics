from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, ApiKey, User
from app.security import generate_api_key, hash_api_key
from app.timezones import validate_server_time_rule


def create_api_key(db: Session, account: Account) -> str:
    """Issue a new key for an account and return the plaintext (shown once)."""
    key, prefix, key_hash = generate_api_key()
    db.add(ApiKey(account_id=account.id, key_prefix=prefix, key_hash=key_hash))
    db.commit()
    return key


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
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        db.add(user)
        db.flush()

    account = Account(
        user_id=user.id,
        label=label,
        broker=broker,
        currency=currency.upper(),
        starting_balance=starting_balance,
        is_demo=is_demo,
        server_timezone=validate_server_time_rule(server_timezone) if server_timezone else None,
    )
    db.add(account)
    db.commit()
    return account, create_api_key(db, account)


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
    if server_timezone is not None:
        account.server_timezone = validate_server_time_rule(server_timezone)
    if currency is not None:
        account.currency = currency.upper()
    if starting_balance is not None:
        account.starting_balance = starting_balance
    db.commit()
    return account
