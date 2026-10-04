"""What the rest of the system asks of a model provider, whichever one the account uses."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict

from scientrag.providers.errors import ProviderError

# answer: the model that writes answers. fast: the cheap model for summaries,
# reranking and classification. embedding: text to vector.
Role = Literal["answer", "fast", "embedding"]


class Message(TypedDict):
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Usage:
    role: Role
    model: str
    input_tokens: int
    output_tokens: int


class ModelProvider(Protocol):
    """One connection serves every role, so one object does chat and embedding."""

    # Calls made through this object, for the caller to save and clear.
    usage: list[Usage]

    def model(self, role: Role) -> str:
        """The model used for this role. Raises ProviderError if none is chosen."""

    async def complete(
        self,
        messages: list[Message],
        *,
        role: Role,
        max_tokens: int,
        system: str | None = None,
        json_output: bool = False,
    ) -> str: ...

    def stream(
        self, messages: list[Message], *, role: Role, max_tokens: int, system: str | None = None
    ) -> AsyncIterator[str]: ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...

    async def list_models(self) -> list[str]:
        """Model ids the key can use, for the model pickers in Settings."""

    async def aclose(self) -> None: ...


def estimated_tokens(texts: list[str]) -> int:
    """Rough token count for providers that do not report one: about four characters each."""
    return sum(len(text) for text in texts) // 4


async def with_retries[T](call: Callable[[], Awaitable[T]], *, attempts: int = 4) -> T:
    """Repeats a call that failed for a passing reason, waiting longer each time."""
    for attempt in range(attempts):
        try:
            return await call()
        except ProviderError as error:
            if not error.retryable or attempt == attempts - 1:
                raise
            await asyncio.sleep(min(error.retry_after or 2 ** (attempt + 1), 30))
    raise AssertionError("unreachable")
