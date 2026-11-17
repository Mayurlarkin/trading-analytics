from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User
from app.security import hash_password, spend_password_time, verify_password

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128  # keeps the hashing work bounded


class WeakPassword(ValueError):
    pass


def find_user_by_email(db: Session, email: str) -> User | None:
    # Compared in lower case so "Me@X.com" and "me@x.com" are the same person on any database.
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def check_password_rules(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise WeakPassword(
            f"password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters long"
        )


def set_password(db: Session, email: str, password: str) -> bool:
    """Set the login password of an existing user. False if there is no such user."""
    check_password_rules(password)
    user = find_user_by_email(db, email)
    if user is None:
        return False
    user.password_hash = hash_password(password)
    db.commit()
    return True


def authenticate(db: Session, email: str, password: str) -> User | None:
    """The user if the email and password are right, else None (never says which was wrong)."""
    user = find_user_by_email(db, email)
    if user is None or user.password_hash is None:
        spend_password_time()
        return None
    return user if verify_password(password, user.password_hash) else None
