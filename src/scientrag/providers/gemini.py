"""Google Gemini API: chat and embeddings with one API key."""

from collections.abc import AsyncIterator
from typing import Any

from scientrag.providers.base import Message, Role, Usage, estimated_tokens, with_retries
from scientrag.providers.defaults import GEMINI_EMBEDDING_DIMENSION
from scientrag.providers.errors import ProviderError
from scientrag.providers.http import new_client, request_json, stream_sse

BASE = "https://generativelanguage.googleapis.com/v1beta"
EMBED_BATCH = 50
# gemini-embedding-2 takes the task as a text prefix, different for questions and passages.
QUERY_PREFIX = "task: search result | query: "
DOCUMENT_PREFIX = "title: none | text: "


class GeminiProvider:
    def __init__(self, api_key: str, models: dict[Role, str]) -> None:
        self._headers = {"x-goog-api-key": api_key}
        self._models = models
        self._client = new_client()
        self.usage: list[Usage] = []

    def model(self, role: Role) -> str:
        return self._models[role]

    def _body(
        self, messages: list[Message], max_tokens: int, system: str | None, json_output: bool
    ) -> dict[str, Any]:
        config: dict[str, Any] = {"maxOutputTokens": max_tokens, "temperature": 0}
        if json_output:
            config["responseMimeType"] = "application/json"
        body: dict[str, Any] = {
            "contents": [
                {
                    "role": "model" if message["role"] == "assistant" else "user",
                    "parts": [{"text": message["content"]}],
                }
                for message in messages
            ],
            "generationConfig": config,
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return body

    def _record(self, role: Role, metadata: dict[str, Any]) -> None:
        self.usage.append(
            Usage(
                role,
                self.model(role),
                metadata.get("promptTokenCount", 0),
                # Thinking tokens are billed as output.
                metadata.get("candidatesTokenCount", 0) + metadata.get("thoughtsTokenCount", 0),
            )
        )

    @staticmethod
    def _text(chunk: dict[str, Any]) -> str:
        candidates = chunk.get("candidates") or [{}]
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(part.get("text", "") for part in parts if not part.get("thought"))

    async def complete(
        self,
        messages: list[Message],
        *,
        role: Role,
        max_tokens: int,
        system: str | None = None,
        json_output: bool = False,
    ) -> str:
        reply = await with_retries(
            lambda: request_json(
                self._client,
                "POST",
                f"{BASE}/models/{self.model(role)}:generateContent",
                headers=self._headers,
                payload=self._body(messages, max_tokens, system, json_output),
            )
        )
        self._record(role, reply.get("usageMetadata", {}))
        return self._text(reply)

    async def stream(
        self, messages: list[Message], *, role: Role, max_tokens: int, system: str | None = None
    ) -> AsyncIterator[str]:
        metadata: dict[str, Any] = {}
        async for chunk in stream_sse(
            self._client,
            f"{BASE}/models/{self.model(role)}:streamGenerateContent?alt=sse",
            headers=self._headers,
            payload=self._body(messages, max_tokens, system, False),
        ):
            metadata = chunk.get("usageMetadata", metadata)
            if text := self._text(chunk):
                yield text
        self._record(role, metadata)

    async def _embed(self, texts: list[str], prefix: str) -> list[list[float]]:
        model = self.model("embedding")
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start : start + EMBED_BATCH]
            payload = {
                "requests": [
                    {
                        "model": f"models/{model}",
                        "content": {"parts": [{"text": prefix + text}]},
                        "output_dimensionality": GEMINI_EMBEDDING_DIMENSION,
                    }
                    for text in batch
                ]
            }
            reply = await with_retries(
                lambda payload=payload: request_json(
                    self._client,
                    "POST",
                    f"{BASE}/models/{model}:batchEmbedContents",
                    headers=self._headers,
                    payload=payload,
                )
            )
            rows = reply.get("embeddings", [])
            if len(rows) != len(batch):
                raise ProviderError("provider_rejected", "wrong number of embeddings returned")
            vectors += [row["values"] for row in rows]
            # The batch endpoint reports no token count.
            self.usage.append(Usage("embedding", model, estimated_tokens(batch), 0))
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, DOCUMENT_PREFIX)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], QUERY_PREFIX))[0]

    async def list_models(self) -> list[str]:
        reply = await request_json(
            self._client, "GET", f"{BASE}/models?pageSize=1000", headers=self._headers
        )
        return sorted(item["name"].removeprefix("models/") for item in reply.get("models", []))

    async def aclose(self) -> None:
        await self._client.aclose()
