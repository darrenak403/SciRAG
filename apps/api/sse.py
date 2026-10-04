"""Server-sent events: the wire format of a streamed answer."""

import json
from collections.abc import AsyncGenerator
from typing import Any

import anyio
from fastapi.responses import StreamingResponse
from starlette.types import Send

# Longest the cleanup of an abandoned stream may take.
CLOSE_SECONDS = 10


def event(name: str, data: Any) -> str:
    """One event. The data is a single line of JSON, so it never breaks the framing."""
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


class EventStream(StreamingResponse):
    """A response that streams events from a generator.

    The generator is closed the moment the client is gone. Left to itself it would
    stay suspended until collected, with whatever it holds open still running.
    A client that leaves cancels the request, so the closing is shielded: what the
    generator cleans up on its way out has to finish.
    """

    def __init__(self, events: AsyncGenerator[str]) -> None:
        super().__init__(
            events,
            media_type="text/event-stream",
            # Proxies must pass each event on as it is written.
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
        self._events = events

    async def stream_response(self, send: Send) -> None:
        try:
            await super().stream_response(send)
        finally:
            with anyio.move_on_after(CLOSE_SECONDS, shield=True):
                await self._events.aclose()
