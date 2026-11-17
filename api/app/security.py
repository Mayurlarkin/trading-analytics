import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import cache

import jwt

API_KEY_PREFIX = "ta_"
_PREFIX_DISPLAY_LEN = 11  # "ta_" + 8 characters, safe to show in lists and logs


def hash_api_key(key: str) -> str:
    """SHA-256 hex digest of an API key.

    A fast hash is appropriate here: keys are 256-bit random values, so there is
    nothing to brute-force (unlike human-chosen passwords, which need bcrypt/argon2).
    """
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return (plaintext_key, display_prefix, key_hash). Show the plaintext only once."""
    key = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, key[:_PREFIX_DISPLAY_LEN], hash_api_key(key)


# --- passwords --------------------------------------------------------------------------
# scrypt from the standard library (no extra dependency). The cost settings are stored inside
# each hash, so they can be raised later without locking anyone out. N=2**15, r=8, p=3 is one
# of the combinations OWASP lists as an acceptable minimum (about 32 MB of memory per login).
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 3
_SALT_BYTES = 16
_KEY_BYTES = 32
_MAX_SCRYPT_N = 2**20  # refuse absurd stored costs instead of exhausting memory


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, maxmem=256 * n * r, dklen=_KEY_BYTES
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """True if the password matches. Any malformed or unsupported hash is simply a no."""
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt" or not 1 < int(n) <= _MAX_SCRYPT_N:
            return False
        digest = _scrypt(password, base64.b64decode(salt, validate=True), int(n), int(r), int(p))
        return hmac.compare_digest(digest, base64.b64decode(expected, validate=True))
    except (ValueError, TypeError):
        return False


@cache
def _decoy_hash() -> str:
    return hash_password("decoy-password-for-timing")


def spend_password_time() -> None:
    """Do the same work as a real check, so an unknown email takes as long as a wrong password."""
    verify_password("not-the-password", _decoy_hash())


# --- login tokens -------------------------------------------------------------------------
_JWT_ALGORITHM = "HS256"


def create_access_token(
    user_id: int, secret: str, expires_in: timedelta, *, now: datetime | None = None
) -> str:
    issued = now or datetime.now(UTC)
    claims = {"sub": str(user_id), "iat": issued, "exp": issued + expires_in}
    return jwt.encode(claims, secret, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> int | None:
    """The user id inside a valid, unexpired token, or None for anything else."""
    try:
        claims = jwt.decode(
            token, secret, algorithms=[_JWT_ALGORITHM], options={"require": ["exp", "sub"]}
        )
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None
