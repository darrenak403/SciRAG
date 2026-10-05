"""From an account to a provider object carrying that account's own key.

The key is decrypted here and lives only inside the provider object. Callers
pass user ids around, never credentials.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio

from scirag.auth.secrets import decrypt_secret
from scirag.db.engine import get_sessionmaker
from scirag.db.models import ProviderConnection, User
from scirag.db.repositories import provider_connections as connections_repo
from scirag.db.repositories import provider_usage as usage_repo
from scirag.providers.base import ModelProvider
from scirag.providers.bedrock import BedrockProvider
from scirag.providers.defaults import models_for
from scirag.providers.errors import ProviderError
from scirag.providers.gemini import GeminiProvider
from scirag.providers.openai_compatible import OpenAICompatibleProvider


def build_provider(connection: ProviderConnection) -> ModelProvider:
    secret = decrypt_secret(connection.secret_encrypted)
    models = models_for(connection.kind, connection.config.get("models", {}))
    if connection.kind == "gemini":
        return GeminiProvider(secret["api_key"], models)
    if connection.kind == "bedrock":
        return BedrockProvider(
            connection.config["region"],
            secret["access_key_id"],
            secret["secret_access_key"],
            models,
        )
    return OpenAICompatibleProvider(connection.config["base_url"], secret["api_key"], models)


# Longest that saving the usage and closing the provider may hold up a cancelled caller.
CLEANUP_SECONDS = 10


@asynccontextmanager
async def connection_provider(connection: ProviderConnection) -> AsyncIterator[ModelProvider]:
    """A provider for this connection.

    On exit the tokens it used are added to the account's usage, in a transaction
    of their own: calls that were made are counted even when the caller fails.
    """
    provider = build_provider(connection)
    try:
        yield provider
    finally:
        # A cancelled caller (a reader who left mid-answer) still pays for the calls made.
        with anyio.move_on_after(CLEANUP_SECONDS, shield=True):
            try:
                if provider.usage:
                    async with get_sessionmaker()() as db:
                        await usage_repo.add(db, connection.user_id, connection.id, provider.usage)
                        await db.commit()
            finally:
                await provider.aclose()


async def active_connection(user_id: uuid.UUID) -> ProviderConnection:
    """The one connection the account uses for every model call."""
    async with get_sessionmaker()() as db:
        user = await db.get(User, user_id)
        connection = (
            await connections_repo.get(db, user_id, user.active_connection_id)
            if user and user.active_connection_id
            else None
        )
    if connection is None:
        raise ProviderError("provider_not_configured")
    return connection


@asynccontextmanager
async def active_provider(user_id: uuid.UUID) -> AsyncIterator[ModelProvider]:
    async with connection_provider(await active_connection(user_id)) as provider:
        yield provider
