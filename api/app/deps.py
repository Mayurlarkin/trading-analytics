from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account
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
