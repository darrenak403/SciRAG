from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from scirag.config import get_settings

# Room for the multipart framing around the largest file allowed.
FORM_OVERHEAD_BYTES = 1024 * 1024


class BodySizeLimit:
    """Refuses a request whose declared length is over the upload limit, before reading it.

    The form parser writes the whole body to disk before the handler, and even
    the session check, gets to run. A body sent without Content-Length is not
    caught here; the handler still enforces the limit on what it reads.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            limit_mb = get_settings().max_upload_mb
            declared = Headers(scope=scope).get("content-length", "")
            if declared.isdigit() and int(declared) > limit_mb * 1024 * 1024 + FORM_OVERHEAD_BYTES:
                response = JSONResponse(
                    {"detail": f"The request is larger than the {limit_mb} MB limit"},
                    status_code=413,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
