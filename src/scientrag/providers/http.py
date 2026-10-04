"""HTTP plumbing shared by the providers reached over plain REST."""

import asyncio
import ipaddress
import json
import re
import socket
from collections.abc import AsyncIterator
from typing import Any

import httpx

from scientrag.config import get_settings
from scientrag.providers.errors import ProviderError, from_http

# Per read: a reply that keeps arriving never trips it, so each call also has a total limit.
TIMEOUT = httpx.Timeout(120, connect=10)
TOTAL_SECONDS = 300
STREAM_TOTAL_SECONDS = 900
# Far above any real reply; stops a server from filling the memory of the process.
MAX_REPLY_BYTES = 64 * 1024 * 1024

# Cloud metadata services. Refused even where private addresses are allowed.
_METADATA = frozenset(
    ipaddress.ip_address(address)
    for address in ("169.254.169.254", "100.100.100.200", "fd00:ec2::254")
)


async def allowed_address(host: str) -> str:
    """Resolves a user-supplied provider host and returns the one address to connect to.

    Cloud metadata and link-local addresses are always refused. Other addresses
    that are not on the public internet are refused unless
    ALLOW_PRIVATE_PROVIDER_URLS is on, which a deployment whose users run their
    own router on the local network needs.
    """
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as error:
        raise ProviderError("provider_unreachable", f"cannot resolve {host}") from error
    address = ipaddress.ip_address(infos[0][4][0])
    checked = getattr(address, "ipv4_mapped", None) or address
    if (
        checked in _METADATA
        or checked.is_link_local
        or checked.is_multicast
        or checked.is_unspecified
        # ::1 sits in a reserved block; loopback is decided below with the private ranges.
        or (checked.is_reserved and not checked.is_loopback)
    ):
        raise ProviderError("provider_rejected", "this address is not allowed")
    if not checked.is_global and not get_settings().allow_private_provider_urls:
        raise ProviderError(
            "provider_rejected", "addresses on a private network are not allowed on this server"
        )
    return str(address)


class _GuardedTransport(httpx.AsyncHTTPTransport):
    """Connects only to the address that was checked.

    Checking a host name and then letting the client resolve it again would let
    its owner answer the check with a public address and the connection with an
    internal one. The request goes to the checked address; the host name is kept
    for the Host header and for the TLS certificate.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        request.url = request.url.copy_with(host=await allowed_address(host))
        request.extensions = {**request.extensions, "sni_hostname": host}
        return await super().handle_async_request(request)


def new_client(*, user_supplied_url: bool = False) -> httpx.AsyncClient:
    """user_supplied_url: the account chose where the requests go, so every address is checked."""
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        # Redirects are not followed: a provider URL must not be able to send the
        # request, and the key in its headers, somewhere else.
        follow_redirects=False,
        # No proxy from the environment: it would connect on the client's behalf.
        trust_env=False,
        transport=_GuardedTransport() if user_supplied_url else None,
    )


def _without_secrets(text: str, headers: dict[str, str]) -> str:
    """Removes the key from a provider's error text, in case the server echoed it."""
    for value in headers.values():
        for secret in {value, value.split(" ")[-1]}:
            if len(secret) >= 8:
                text = text.replace(secret, "[redacted]")
    return text


def _provider_error(status: int, body: bytes, response: httpx.Response) -> ProviderError:
    """The provider's own error text. A body in any other shape is not passed on:
    a user-supplied URL could point at something whose replies are not ours to show."""
    message: str | None = None
    retry_after: float | None = None
    value = response.headers.get("retry-after", "")
    if value.replace(".", "", 1).isdigit():
        retry_after = float(value)
    try:
        error = json.loads(body)["error"]
    except ValueError, KeyError, TypeError:
        error = None
    if isinstance(error, dict):
        details = error.get("details")
        parts = [error.get("message"), error.get("status"), error.get("code")]
        message = " ".join(str(part) for part in parts if part)
        if details:
            text = json.dumps(details)
            message += " " + text[:400]
            # Gemini says how long to wait in the body, not in a header.
            if delay := re.search(r'"retryDelay": "(\d+(?:\.\d+)?)s"', text):
                retry_after = float(delay.group(1))
    elif error is not None:
        message = str(error)
    if message:
        message = _without_secrets(message, dict(response.request.headers))
    return from_http(status, message, retry_after=retry_after)


async def _read(response: httpx.Response) -> bytes:
    body = bytearray()
    async for piece in response.aiter_bytes():
        body += piece
        if len(body) > MAX_REPLY_BYTES:
            raise ProviderError("provider_rejected", "the reply was too large")
    return bytes(body)


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        async with asyncio.timeout(TOTAL_SECONDS):
            async with client.stream(method, url, headers=headers, json=payload) as response:
                body = await _read(response)
    except (httpx.HTTPError, TimeoutError) as error:
        raise ProviderError("provider_unreachable", type(error).__name__) from error
    if response.is_error:
        raise _provider_error(response.status_code, body, response)
    try:
        reply = json.loads(body)
    except ValueError as error:
        raise ProviderError("provider_rejected", "the reply was not JSON") from error
    if not isinstance(reply, dict):
        raise ProviderError("provider_rejected", "the reply was not a JSON object")
    return reply


async def stream_sse(
    client: httpx.AsyncClient, url: str, *, headers: dict[str, str], payload: dict[str, Any]
) -> AsyncIterator[dict[str, Any]]:
    """Yields the JSON object of each server-sent event of a streaming reply."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + STREAM_TOTAL_SECONDS
    try:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            if response.is_error:
                raise _provider_error(response.status_code, await _read(response), response)
            async for line in response.aiter_lines():
                if loop.time() > deadline:
                    raise ProviderError("provider_unreachable", "the reply took too long")
                data = line.removeprefix("data:").strip()
                if not line.startswith("data:") or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    yield event
    except httpx.HTTPError as error:
        raise ProviderError("provider_unreachable", type(error).__name__) from error
