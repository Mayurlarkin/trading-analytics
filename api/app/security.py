import hashlib
import secrets

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
