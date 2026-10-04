"""Test setup: a separate PostgreSQL database, a throwaway storage directory, a throwaway key.

The environment is changed before anything from the project is imported, because
settings are read once and cached.
"""

import os
import shutil
import tempfile
from collections.abc import AsyncIterator, Iterator

from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url

TEST_DATABASE = "scientrag_test"
_dev_url = make_url(os.environ["DATABASE_URL"])
os.environ["DATABASE_URL"] = _dev_url.set(database=TEST_DATABASE).render_as_string(
    hide_password=False
)
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="scientrag-test-storage-")
os.environ["SECRETS_KEY"] = Fernet.generate_key().decode()
os.environ["ALLOW_REGISTRATION"] = "true"
# Small, so the size-limit test does not have to build a 50 MB file.
os.environ["MAX_UPLOAD_MB"] = "1"
# Tests keep their traces in memory; nothing is sent to the tracing service.
os.environ.pop("OTLP_ENDPOINT", None)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from apps.api.main import app  # noqa: E402
from scientrag.auth import login_limiter  # noqa: E402
from scientrag.db.engine import get_engine, get_sessionmaker  # noqa: E402
from scientrag.ingestion.queue import create_tables  # noqa: E402

PASSWORD = "correct horse battery"


def pdf_bytes(body: str = "one") -> bytes:
    """Bytes that pass the PDF check. Different bodies give different files."""
    return b"%PDF-1.7\n" + body.encode()


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    return Config("alembic.ini")


@pytest.fixture(scope="session", autouse=True)
def database(alembic_config: Config) -> Iterator[None]:
    """Creates the test database from the migrations, and drops it afterwards."""
    admin = create_engine(_dev_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    command.upgrade(alembic_config, "head")
    create_tables()
    yield
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(autouse=True)
async def clean_state() -> None:
    """Every test starts with empty tables, empty storage and no recorded login failures."""
    async with get_engine().begin() as connection:
        await connection.execute(text("TRUNCATE users, authors CASCADE"))
    shutil.rmtree(os.environ["STORAGE_DIR"])
    os.mkdir(os.environ["STORAGE_DIR"])
    login_limiter.reset()


USABLE = {
    "checked_at": "2026-01-01T00:00:00+00:00",
    "checks": [],
    "usable": True,
    "rerank_disabled": False,
}


@pytest.fixture(autouse=True)
def connection_check(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Saving a connection tests it against the real provider. Tests have no real key,
    so the test is replaced by a result the test can change: by default, everything works."""
    result = dict(USABLE)

    async def check_connection(db: AsyncSession, connection) -> dict:
        connection.capabilities = dict(result)
        return connection.capabilities

    monkeypatch.setattr("apps.api.routers.providers.check_connection", check_connection)
    return result


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient, email: str) -> None:
    response = await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text


@pytest.fixture
async def anon() -> AsyncIterator[AsyncClient]:
    """A client that is not signed in."""
    async with _client() as client:
        yield client


@pytest.fixture
async def alice() -> AsyncIterator[AsyncClient]:
    async with _client() as client:
        await _register(client, "alice@example.com")
        yield client


@pytest.fixture
async def bob() -> AsyncIterator[AsyncClient]:
    async with _client() as client:
        await _register(client, "bob@example.com")
        yield client
