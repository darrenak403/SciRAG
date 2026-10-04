"""Importing this package registers every table on Base.metadata."""

from scientrag.db.models.author import Author, PaperAuthor
from scientrag.db.models.chat import ChatMessage, ChatSession, MessageSource
from scientrag.db.models.ingestion import Chunk, IngestionRun, PaperSection, PaperSummary
from scientrag.db.models.paper import Paper, PaperStatus
from scientrag.db.models.provider_connection import ProviderConnection
from scientrag.db.models.provider_usage import ProviderUsage
from scientrag.db.models.session import Session
from scientrag.db.models.user import User

__all__ = [
    "Author",
    "ChatMessage",
    "ChatSession",
    "Chunk",
    "IngestionRun",
    "MessageSource",
    "Paper",
    "PaperAuthor",
    "PaperSection",
    "PaperStatus",
    "PaperSummary",
    "ProviderConnection",
    "ProviderUsage",
    "Session",
    "User",
]
