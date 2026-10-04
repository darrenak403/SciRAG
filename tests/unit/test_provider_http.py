"""The OpenAI-compatible adapter against a small local server, and the address check."""

import asyncio
import json
import socket
from collections.abc import AsyncIterator

import pytest

from scientrag.config import get_settings
from scientrag.providers.errors import ProviderError
from scientrag.providers.http import allowed_address
from scientrag.providers.openai_compatible import OpenAICompatibleProvider

KEY = "test-router-key-12345678"


@pytest.fixture
def private_urls_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "allow_private_provider_urls", True)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "::1",
        "10.0.0.5",
        "192.168.1.10",
        "172.16.0.1",
        "100.64.0.1",  # carrier-grade NAT, also used inside clouds
        "169.254.169.254",
        "::ffff:169.254.169.254",
        "0.0.0.0",
    ],
)
async def test_addresses_inside_the_network_are_refused(address: str):
    with pytest.raises(ProviderError) as raised:
        await allowed_address(address)
    assert raised.value.code == "provider_rejected"


async def test_a_public_address_is_allowed():
    assert await allowed_address("8.8.8.8") == "8.8.8.8"


@pytest.mark.parametrize(
    "address", ["169.254.169.254", "100.100.100.200", "fd00:ec2::254", "::ffff:169.254.169.254"]
)
async def test_metadata_addresses_are_refused_even_where_private_ones_are_allowed(
    private_urls_allowed: None, address: str
):
    with pytest.raises(ProviderError):
        await allowed_address(address)


async def test_private_addresses_can_be_allowed_by_the_deployment(private_urls_allowed: None):
    assert await allowed_address("10.0.0.5") == "10.0.0.5"
    assert await allowed_address("127.0.0.1") == "127.0.0.1"


class Server:
    """Answers every request with the next queued (status, body) and records what it got."""

    def __init__(self) -> None:
        self.replies: list[tuple[int, dict]] = []
        self.requests: list[dict] = []
        self.port = 0

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = (await reader.readuntil(b"\r\n\r\n")).decode()
        lines = head.split("\r\n")
        pairs = (line.split(": ", 1) for line in lines[1:] if ": " in line)
        headers = {name.lower(): value for name, value in pairs}
        body = await reader.readexactly(int(headers.get("content-length", 0)))
        self.requests.append(
            {"line": lines[0], "headers": headers, "json": json.loads(body) if body else None}
        )
        status, reply = self.replies.pop(0)
        payload = json.dumps(reply).encode()
        writer.write(
            f"HTTP/1.1 {status} X\r\ncontent-type: application/json\r\n"
            f"content-length: {len(payload)}\r\nconnection: close\r\n\r\n".encode()
            + payload
        )
        await writer.drain()
        writer.close()


@pytest.fixture
async def server() -> AsyncIterator[Server]:
    server = Server()
    # Wherever "localhost" leads on this machine: IPv4 or IPv6 loopback.
    loopback = socket.getaddrinfo("localhost", None, type=socket.SOCK_STREAM)[0][4][0]
    listener = await asyncio.start_server(server.handle, loopback, 0)
    server.port = listener.sockets[0].getsockname()[1]
    yield server
    listener.close()
    await listener.wait_closed()


@pytest.fixture
async def provider(server: Server) -> AsyncIterator[OpenAICompatibleProvider]:
    provider = OpenAICompatibleProvider(
        f"http://localhost:{server.port}/v1",
        KEY,
        {"answer": "big", "fast": "small", "embedding": "embed"},
    )
    yield provider
    await provider.aclose()


async def test_a_local_router_is_refused_unless_the_deployment_allows_it(
    server: Server, provider: OpenAICompatibleProvider
):
    with pytest.raises(ProviderError) as raised:
        await provider.list_models()

    assert raised.value.code == "provider_rejected"
    assert server.requests == []


async def test_chat_and_embeddings_reach_the_router_with_the_key(
    private_urls_allowed: None, server: Server, provider: OpenAICompatibleProvider
):
    server.replies = [
        (
            200,
            {
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 2},
            },
        ),
        (200, {"data": [{"index": 1, "embedding": [0.2]}, {"index": 0, "embedding": [0.1]}]}),
        (200, {"data": [{"id": "b"}, {"id": "a"}, {"name": "no id"}, "junk"]}),
    ]

    assert (
        await provider.complete([{"role": "user", "content": "hi"}], role="fast", max_tokens=5)
        == "hello"
    )
    # Rows are put back in the order of the input.
    assert await provider.embed_documents(["one", "two"]) == [[0.1], [0.2]]
    assert await provider.list_models() == ["a", "b"]

    chat, embeddings, models = server.requests
    assert chat["line"] == "POST /v1/chat/completions HTTP/1.1"
    assert chat["json"]["model"] == "small"
    # The connection goes to the checked address; the server still sees the name it was given.
    assert chat["headers"]["host"] == f"localhost:{server.port}"
    assert chat["headers"]["authorization"] == f"Bearer {KEY}"
    assert embeddings["json"] == {"model": "embed", "input": ["one", "two"]}
    assert models["line"] == "GET /v1/models HTTP/1.1"
    assert [(call.role, call.input_tokens, call.output_tokens) for call in provider.usage] == [
        ("fast", 7, 2),
        ("embedding", 1, 0),
    ]


async def test_a_key_echoed_in_an_error_is_removed(
    private_urls_allowed: None, server: Server, provider: OpenAICompatibleProvider
):
    server.replies = [(401, {"error": {"message": f"Incorrect API key provided: {KEY}"}})]

    with pytest.raises(ProviderError) as raised:
        await provider.complete([{"role": "user", "content": "hi"}], role="fast", max_tokens=5)

    assert raised.value.code == "invalid_key"
    assert KEY not in str(raised.value)
    assert "[redacted]" in str(raised.value)


async def test_a_rate_limit_is_retried_after_the_wait_the_provider_asks_for(
    private_urls_allowed: None,
    server: Server,
    provider: OpenAICompatibleProvider,
    monkeypatch: pytest.MonkeyPatch,
):
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr("scientrag.providers.base.asyncio.sleep", sleep)
    limited = {
        "error": {
            "message": "You exceeded your current quota, please check your plan and billing",
            "status": "RESOURCE_EXHAUSTED",
            "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"}],
        }
    }
    server.replies = [(429, limited), (200, {"data": [{"index": 0, "embedding": [0.5]}]})]

    assert await provider.embed_query("one") == [0.5]
    assert waits == [7]
    assert len(server.requests) == 2


async def test_a_reply_that_is_not_what_was_asked_for_is_rejected(
    private_urls_allowed: None, server: Server, provider: OpenAICompatibleProvider
):
    server.replies = [(200, {"data": []}), (200, {"choices": []})]

    with pytest.raises(ProviderError) as wrong_count:
        await provider.embed_documents(["one"])
    with pytest.raises(ProviderError) as no_message:
        await provider.complete([{"role": "user", "content": "hi"}], role="fast", max_tokens=5)

    assert wrong_count.value.code == no_message.value.code == "provider_rejected"
