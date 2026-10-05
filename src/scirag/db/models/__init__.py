"""Importing this package registers every table on Base.metadata."""

from scirag.db.models.author import Author, PaperAuthor
from scirag.db.models.chat import ChatMessage, ChatSession, MessageSource
from scirag.db.models.collection import Collection, CollectionPaper
from scirag.db.models.ingestion import Chunk, IngestionRun, PaperSection, PaperSummary
from scirag.db.models.paper import Paper, PaperStatus
from scirag.db.models.provider_connection import ProviderConnection
from scirag.db.models.provider_usage import ProviderUsage
from scirag.db.models.session import Session
from scirag.db.models.user import User

__all__ = [
    "Author",
    "ChatMessage",
    "ChatSession",
    "Chunk",
    "Collection",
    "CollectionPaper",
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
