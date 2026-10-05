"""Session tokens: random, sent in a cookie, stored only as a hash."""

import hashlib
import secrets

COOKIE_NAME = "scirag_session"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # The token is 32 random bytes, so a plain SHA-256 is enough: there is
    # nothing to brute-force, unlike a password.
    return hashlib.sha256(token.encode()).hexdigest()
