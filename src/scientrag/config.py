"""Application settings, read from environment variables only."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:5432/db
    database_url: str
    # Fernet key that encrypts the model-provider keys users save.
    secrets_key: str
    storage_dir: Path = Path("/data/storage")
    session_ttl_days: int = 30
    max_upload_mb: int = 50
    allow_registration: bool = True
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
