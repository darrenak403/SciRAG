"""Any server that speaks the OpenAI REST API, such as a self-hosted model router."""

from collections.abc import AsyncIterator
from typing import Any

from scientrag.providers.base import Message, Role, Usage, estimated_tokens, with_retries
from scientrag.providers.errors import ProviderError
from scientrag.providers.http import new_client, request_json, stream_sse

EMBED_BATCH = 64


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, models: dict[Role, str]) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"authorization": f"Bearer {api_key}"}
        self._models = models
        self._client = new_client(user_supplied_url=True)
        self.usage: list[Usage] = []

    def model(self, role: Role) -> str:
        if role not in self._models:
            raise ProviderError("capability_missing", f"no model is chosen for the {role} role")
        return self._models[role]

    def _body(
        self, messages: list[Message], role: Role, max_tokens: int, system: str | None
    ) -> dict[str, Any]:
        chat = [{"role": "system", "content": system}] if system else []
        return {
            "model": self.model(role),
            "messages": chat + list(messages),
            "max_tokens": max_tokens,
            "temperature": 0,
        }

    def _record(self, role: Role, usage: dict[str, Any] | None) -> None:
        usage = usage or {}
        self.usage.append(
            Usage(
                role,
                self.model(role),
                usage.get("prompt_tokens") or 0,
                usage.get("completion_tokens") or 0,
            )
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await with_retries(
            lambda: request_json(
                self._client, "POST", f"{self._base}{path}", headers=self._headers, payload=payload
            )
        )

    async def complete(
        self,
        messages: list[Message],
        *,
        role: Role,
        max_tokens: int,
        system: str | None = None,
        json_output: bool = False,
    ) -> str:
        # Said outright: some routers stream the reply unless told not to.
        payload = self._body(messages, role, max_tokens, system) | {"stream": False}
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        reply = await self._post("/chat/completions", payload)
        self._record(role, reply.get("usage"))
        try:
            return reply["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("provider_rejected", "the reply had no message") from error

    async def stream(
        self, messages: list[Message], *, role: Role, max_tokens: int, system: str | None = None
    ) -> AsyncIterator[str]:
        payload = self._body(messages, role, max_tokens, system)
        payload |= {"stream": True, "stream_options": {"include_usage": True}}
        usage: dict[str, Any] | None = None
        async for chunk in stream_sse(
            self._client, f"{self._base}/chat/completions", headers=self._headers, payload=payload
        ):
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices") or []:
                if text := (choice.get("delta") or {}).get("content"):
                    yield text
        self._record(role, usage)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        model = self.model("embedding")
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start : start + EMBED_BATCH]
            reply = await self._post("/embeddings", {"model": model, "input": batch})
            rows = sorted(reply.get("data") or [], key=lambda row: row.get("index", 0))
            if len(rows) != len(batch):
                raise ProviderError("provider_rejected", "wrong number of embeddings returned")
            vectors += [row["embedding"] for row in rows]
            reported = (reply.get("usage") or {}).get("prompt_tokens")
            self.usage.append(Usage("embedding", model, reported or estimated_tokens(batch), 0))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]

    async def list_models(self) -> list[str]:
        reply = await request_json(
            self._client, "GET", f"{self._base}/models", headers=self._headers
        )
        items = reply.get("data")
        return sorted(
            item["id"]
            for item in (items if isinstance(items, list) else [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )

    async def aclose(self) -> None:
        await self._client.aclose()
