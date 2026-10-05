from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from apps.api.middleware import BodySizeLimit
from apps.api.routers import auth, chats, chunks, collections, health, papers, providers
from scirag.auth.secrets import get_fernet
from scirag.config import get_settings
from scirag.db.engine import get_engine
from scirag.telemetry.tracing import get_tracer_provider


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings()
    # Fail at startup, not on the first saved key, when SECRETS_KEY is malformed.
    try:
        get_fernet()
    except ValueError as error:
        raise RuntimeError(
            "SECRETS_KEY must be a Fernet key (32 url-safe base64-encoded bytes). "
            "See .env.example for how to generate one."
        ) from error
    yield
    # Sends the traces still waiting in memory.
    get_tracer_provider().shutdown()
    await get_engine().dispose()


app = FastAPI(title="SciRAG API", lifespan=lifespan)
app.add_middleware(BodySizeLimit)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(papers.router)
app.include_router(providers.router)
app.include_router(chats.router)
app.include_router(collections.router)
app.include_router(chunks.router)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    """The default answer without "input": that field echoes what was sent, which
    can be a password or a provider key."""
    details = [
        {key: value for key, value in item.items() if key != "input"} for item in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(details)})
