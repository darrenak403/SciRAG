"""Importing this package registers every table on Base.metadata."""

from scientrag.db.models.author import Author, PaperAuthor
from scientrag.db.models.paper import Paper, PaperStatus
from scientrag.db.models.provider_connection import ProviderConnection
from scientrag.db.models.session import Session
from scientrag.db.models.user import User

__all__ = [
    "Author",
    "Paper",
    "PaperAuthor",
    "PaperStatus",
    "ProviderConnection",
    "Session",
    "User",
]
