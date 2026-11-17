from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas_analytics import TokenOut, UserOut
from app.security import create_access_token
from app.services.users import MAX_PASSWORD_LENGTH, authenticate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenOut:
    """Exchange email (in the ``username`` field) and password for a login token.

    Send it on later requests as ``Authorization: Bearer <token>``. In /docs, use Authorize.
    """
    # Cap the length before hashing so a huge "password" cannot be used to burn CPU.
    user = None
    if len(form.password) <= MAX_PASSWORD_LENGTH:
        user = authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    settings = get_settings()
    lifetime = timedelta(minutes=settings.jwt_expire_minutes)
    token = create_access_token(user.id, settings.jwt_secret, lifetime)
    return TokenOut(access_token=token, expires_in=int(lifetime.total_seconds()))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email)
