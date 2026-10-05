"""Encrypts the provider credentials users save, with the server's SECRETS_KEY."""

import json
from functools import lru_cache

from cryptography.fernet import Fernet

from scirag.config import get_settings


@lru_cache
def get_fernet() -> Fernet:
    """Raises ValueError when SECRETS_KEY is not a valid Fernet key."""
    return Fernet(get_settings().secrets_key)


def encrypt_secret(secret: dict[str, str]) -> str:
    return get_fernet().encrypt(json.dumps(secret).encode()).decode()


def decrypt_secret(token: str) -> dict[str, str]:
    return json.loads(get_fernet().decrypt(token.encode()))
