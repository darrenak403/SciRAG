"""AWS Bedrock: chat through the Converse API, embeddings through Amazon Titan."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from scirag.providers.base import Message, Role, Usage, with_retries
from scirag.providers.defaults import DEFAULT_MODELS, TITAN_EMBEDDING_DIMENSION
from scirag.providers.errors import ProviderError, from_aws

# Titan embeds one text per request, so several run at once.
EMBED_CONCURRENCY = 8
JSON_INSTRUCTION = "Reply with a single JSON value and nothing else."


def _call[T](function: Callable[..., T], **arguments: Any) -> T:
    try:
        return function(**arguments)
    except ClientError as error:
        details = error.response.get("Error", {})
        raise from_aws(details.get("Code", ""), details.get("Message")) from error
    except BotoCoreError as error:
        raise ProviderError("provider_unreachable", type(error).__name__) from error


class BedrockProvider:
    def __init__(
        self, region: str, access_key_id: str, secret_access_key: str, models: dict[Role, str]
    ) -> None:
        self._models = models
        # Retries are done here, with the same rules as the other providers.
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(retries={"max_attempts": 1}, connect_timeout=10, read_timeout=120),
        )
        self.usage: list[Usage] = []

    def model(self, role: Role) -> str:
        return self._models[role]

    def _arguments(
        self,
        messages: list[Message],
        role: Role,
        max_tokens: int,
        system: str | None,
        json_output: bool,
    ) -> dict[str, Any]:
        # Converse has no JSON mode; the instruction is the only lever.
        instructions = [
            text for text in (system, JSON_INSTRUCTION if json_output else None) if text
        ]
        arguments: dict[str, Any] = {
            "modelId": self.model(role),
            "messages": [
                {"role": message["role"], "content": [{"text": message["content"]}]}
                for message in messages
            ],
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0},
        }
        if instructions:
            arguments["system"] = [{"text": "\n\n".join(instructions)}]
        return arguments

    def _record(self, role: Role, usage: dict[str, Any]) -> None:
        self.usage.append(
            Usage(role, self.model(role), usage.get("inputTokens", 0), usage.get("outputTokens", 0))
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
        arguments = self._arguments(messages, role, max_tokens, system, json_output)
        reply = await with_retries(
            lambda: asyncio.to_thread(_call, self._client.converse, **arguments)
        )
        self._record(role, reply.get("usage", {}))
        content = reply.get("output", {}).get("message", {}).get("content", [])
        return "".join(block.get("text", "") for block in content)

    async def stream(
        self, messages: list[Message], *, role: Role, max_tokens: int, system: str | None = None
    ) -> AsyncIterator[str]:
        arguments = self._arguments(messages, role, max_tokens, system, False)
        reply = await asyncio.to_thread(_call, self._client.converse_stream, **arguments)
        events = iter(reply["stream"])
        while True:
            # The event stream blocks while it waits for the next piece.
            event = await asyncio.to_thread(_call, lambda: next(events, None))
            if event is None:
                break
            if text := event.get("contentBlockDelta", {}).get("delta", {}).get("text"):
                yield text
            if "metadata" in event:
                self._record(role, event["metadata"].get("usage", {}))

    async def _embed_one(self, text: str, limit: asyncio.Semaphore) -> list[float]:
        model = self.model("embedding")
        body = json.dumps(
            {"inputText": text, "dimensions": TITAN_EMBEDDING_DIMENSION, "normalize": True}
        )

        def invoke() -> dict[str, Any]:
            reply = _call(self._client.invoke_model, modelId=model, body=body)
            return json.loads(reply["body"].read())

        async with limit:
            reply = await with_retries(lambda: asyncio.to_thread(invoke))
        self.usage.append(Usage("embedding", model, reply.get("inputTextTokenCount", 0), 0))
        return reply["embedding"]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        limit = asyncio.Semaphore(EMBED_CONCURRENCY)
        return list(await asyncio.gather(*(self._embed_one(text, limit) for text in texts)))

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]

    async def list_models(self) -> list[str]:
        # Listing needs a different AWS permission than calling; offer the models known to work.
        return sorted(set(DEFAULT_MODELS["bedrock"].values()) | set(self._models.values()))

    async def aclose(self) -> None:
        await asyncio.to_thread(self._client.close)
