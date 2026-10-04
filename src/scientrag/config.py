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
    qdrant_url: str = "http://qdrant:6333"
    # Lets accounts point an OpenAI-compatible connection at a private address,
    # for a model router on the local network. Leave off on a public server.
    allow_private_provider_urls: bool = False
    # Papers the worker processes at the same time. Each one can take 2-3 GB while parsing.
    ingest_concurrency: int = 1
    max_paper_pages: int = 150
    chunk_max_tokens: int = 400
    # Off: no model call to summarize each paper; the paper is found by its title and opening text.
    summarize_papers: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
