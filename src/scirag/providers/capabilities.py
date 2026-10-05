"""Tries everything the system needs from a connection and reports each result."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from scirag.db.models import ProviderConnection
from scirag.providers.base import ModelProvider
from scirag.providers.errors import ProviderError
from scirag.providers.resolve import connection_provider

# Without these the connection cannot serve an account at all.
REQUIRED = ("authentication", "chat", "streaming", "embeddings")
PROMPT = [{"role": "user", "content": "Reply with the single word: ready"}]
JSON_PROMPT = [{"role": "user", "content": "Reply with this JSON array and nothing else: [1, 2]"}]


async def _chat(provider: ModelProvider) -> str | None:
    for role in ("answer", "fast"):
        if not (await provider.complete(PROMPT, role=role, max_tokens=64)).strip():
            raise ProviderError("capability_missing", f"the {role} model returned no text")
    return None


async def _streaming(provider: ModelProvider) -> str | None:
    pieces = [piece async for piece in provider.stream(PROMPT, role="answer", max_tokens=64)]
    if not "".join(pieces).strip():
        raise ProviderError("capability_missing", "the stream carried no text")
    return None


async def _structured_output(provider: ModelProvider) -> str | None:
    reply = await provider.complete(JSON_PROMPT, role="fast", max_tokens=64, json_output=True)
    try:
        json.loads(reply)
    except ValueError as error:
        raise ProviderError("capability_missing", "the fast model did not return JSON") from error
    return None


async def _embeddings(provider: ModelProvider) -> str | None:
    vector = await provider.embed_query("ready")
    if not vector:
        raise ProviderError("capability_missing", "the embedding model returned no vector")
    return f"{len(vector)} dimensions"


CHECKS = {
    "chat": _chat,
    "streaming": _streaming,
    "structured_output": _structured_output,
    "embeddings": _embeddings,
}
# Failures that say the key itself or the route to the provider is the problem.
AUTHENTICATION_FAILURES = ("invalid_key", "provider_unreachable")


async def check_provider(provider: ModelProvider) -> dict[str, Any]:
    """Runs every check. The result is stored on the connection and shown in Settings."""
    checks = []
    blocked: ProviderError | None = None
    for name, run in CHECKS.items():
        if blocked is not None:
            # Nothing else can work without a valid key, so do not burn calls finding out.
            checks.append(_failed(name, blocked))
            continue
        try:
            checks.append(
                {"check": name, "ok": True, "error_code": None, "message": await run(provider)}
            )
        except ProviderError as error:
            checks.append(_failed(name, error))
            if error.code in AUTHENTICATION_FAILURES:
                blocked = error

    authentication = (
        _failed("authentication", blocked)
        if blocked
        else {"check": "authentication", "ok": True, "error_code": None, "message": None}
    )
    checks.insert(0, authentication)
    passed = {check["check"] for check in checks if check["ok"]}
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "usable": all(name in passed for name in REQUIRED),
        # Reranking asks the fast model for JSON; without it, ranking stays as retrieved.
        "rerank_disabled": "structured_output" not in passed,
    }


def _failed(name: str, error: ProviderError) -> dict[str, Any]:
    return {"check": name, "ok": False, "error_code": error.code, "message": str(error)}


async def check_connection(db: AsyncSession, connection: ProviderConnection) -> dict[str, Any]:
    """Tests a saved connection with its own key and stores the result on it."""
    async with connection_provider(connection) as provider:
        result = await check_provider(provider)
    connection.capabilities = result
    return result
