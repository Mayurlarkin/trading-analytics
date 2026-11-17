from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Account, User
from app.security import decode_access_token
from app.services.accounts import find_account_by_api_key

# Registers an "Authorize" button in the interactive docs at /docs.
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key_account(
    api_key: str | None = Depends(_api_key_header),
    db: Session = Depends(get_db),
) -> Account:
    """Authenticate a machine client (EA/script) and return the account it may write to."""
    account = find_account_by_api_key(db, api_key) if api_key else None
    if account is None:
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    return account


# Registers the "username + password" login form behind the Authorize button in /docs.
_bearer = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(token: str | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    """Authenticate a person (dashboard or /docs) from their login token."""
    user_id = decode_access_token(token, get_settings().jwt_secret) if token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status_code=401, detail="not authenticated", headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def get_owned_account(
    account_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Account:
    """The account from the URL, but only if it belongs to the logged-in user.

    Someone else's account answers 404, the same as one that does not exist, so ids cannot be
    probed."""
    account = db.scalar(select(Account).where(Account.id == account_id, Account.user_id == user.id))
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    return account
