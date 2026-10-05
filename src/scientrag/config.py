"""Application settings, read from environment variables only."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
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
    # Answering a question: passages each search (meaning, keywords) brings back,
    # how many of the merged list go to the reranker, and how many reach the model.
    search_candidates: int = 50
    # How the two rankings are merged: rrf, dbsf, or none for the search by meaning alone.
    search_fusion: Literal["rrf", "dbsf", "none"] = "rrf"
    rerank_candidates: int = 30
    context_chunks: int = 8
    context_max_tokens: int = 6000
    answer_max_tokens: int = 2048
    # Off: passages go to the model in the order the search returned them.
    rerank_enabled: bool = True
    fast_model_timeout_seconds: float = 20
    # Comparing and synthesizing across papers. At most this many papers are looked at
    # (the most relevant ones when the scope holds more), each with this many passages.
    multi_paper_max_papers: int = Field(20, ge=1)
    multi_paper_chunks: int = Field(3, ge=1)
    # Calls to the fast model that run at the same time while evidence is gathered.
    multi_paper_parallel_calls: int = Field(4, ge=1)
    # A passage the fast model scores below this (0-10) is left out of a synthesis.
    evidence_min_relevance: int = 4
    multi_paper_context_tokens: int = 16000
    # A table or a review of many papers is longer than the answer to one question.
    multi_paper_answer_tokens: int = 4096
    # Where traces of answered questions are sent (OTLP over HTTP). Unset: nowhere.
    otlp_endpoint: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
