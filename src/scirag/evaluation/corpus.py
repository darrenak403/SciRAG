"""Puts a dataset's papers into the system, under an account of their own.

The papers go through the same chunk, embed and index steps as an upload, so a
run measures what users get. Each chunk size has its own account: the same
paper chunked two ways is two papers, owned by two accounts, and a search by
one account never sees the other's chunks.
"""

import asyncio
import hashlib
import json
import os
import secrets
import uuid
from typing import Any

from sqlalchemy import select

from scirag.auth.passwords import hash_password
from scirag.auth.secrets import encrypt_secret
from scirag.db.engine import get_sessionmaker
from scirag.db.models import Chunk, Paper, PaperStatus, ProviderConnection, User
from scirag.db.repositories import papers as papers_repo
from scirag.db.repositories import provider_connections as connections_repo
from scirag.db.repositories import users as users_repo
from scirag.evaluation.datasets.base import EvalPaper
from scirag.ingestion import steps
from scirag.providers.capabilities import check_connection
from scirag.storage import get_storage

# A domain that cannot receive mail or be registered: these accounts own papers, nothing else.
EMAIL_DOMAIN = "eval.invalid"
LABEL = "evaluation"
# The steps of an upload that come after parsing.
STEPS = ("chunk", "embed", "index", "validate")
PAPERS_AT_ONCE = 3


def account_email(chunk_max_tokens: int) -> str:
    return f"chunk-{chunk_max_tokens}@{EMAIL_DOMAIN}"


async def ensure_account(email: str, provider: dict[str, Any]) -> ProviderConnection:
    """The evaluation account with a tested connection. provider names the environment
    variable that holds the key; the key itself is never written to a config file."""
    key = os.environ.get(provider["key_env"])
    if not key:
        raise SystemExit(f"Set {provider['key_env']} to the key the evaluation should use.")
    config: dict[str, Any] = {"models": provider.get("models", {})}
    if "base_url" in provider:
        config["base_url"] = provider["base_url"]
    async with get_sessionmaker()() as db:
        user = await users_repo.get_by_email(db, email)
        if user is None:
            # A password nobody knows: nobody signs in to this account.
            user = await users_repo.create(db, email, hash_password(secrets.token_urlsafe(32)))
        connection = (
            await connections_repo.get(db, user.id, user.active_connection_id)
            if user.active_connection_id
            else None
        )
        if connection is None:
            connection = await connections_repo.create(
                db,
                user_id=user.id,
                kind=provider["kind"],
                label=LABEL,
                config=config,
                secret_encrypted=encrypt_secret({"api_key": key}),
                secret_last4=key[-4:],
            )
            user.active_connection_id = connection.id
            # The test records its usage in a transaction of its own, which has to see the row.
            await db.commit()
            await check_connection(db, connection)
        else:
            # The key or the models may have changed since the account was made.
            connection.config = config
            connection.secret_encrypted = encrypt_secret({"api_key": key})
            connection.secret_last4 = key[-4:]
        await db.commit()
        await db.refresh(connection)
    if not (connection.capabilities or {}).get("usable"):
        raise SystemExit(
            f"The {provider['kind']} connection did not pass its test. The test runs once, "
            "when the account is made: run with --clean and start again."
        )
    return connection


async def _ensure_paper(owner_id: uuid.UUID, dataset: str, paper: EvalPaper) -> uuid.UUID:
    """The indexed copy of the paper, made on first use and found again afterwards."""
    digest = hashlib.sha256(f"{dataset}:{paper.key}".encode()).hexdigest()
    async with get_sessionmaker()() as db:
        row = await papers_repo.get_by_sha256(db, owner_id, digest)
        if row is None:
            paper_id = uuid.uuid7()
            row = await papers_repo.create(
                db,
                paper_id=paper_id,
                owner_id=owner_id,
                title=paper.title[:1000],
                original_filename=f"{paper.key}.pdf"[:255],
                file_sha256=digest,
                # There is no uploaded file: the parsed document is put in place below.
                storage_key=f"papers/{paper_id}/original.pdf",
            )
            await db.commit()
        paper_id, ready = row.id, row.status == PaperStatus.READY
    if not ready:
        document = json.dumps(paper.document.model_dump(mode="json")).encode()
        await asyncio.to_thread(get_storage().put, steps.document_key(paper_id), [document])
        for step in STEPS:
            await steps.WORK[step](paper_id)
    return paper_id


async def ensure_papers(
    owner_id: uuid.UUID, dataset: str, papers: list[EvalPaper]
) -> dict[str, uuid.UUID]:
    """Indexes the papers that are not there yet. Returns the paper id of each key."""
    limit = asyncio.Semaphore(PAPERS_AT_ONCE)

    async def one(paper: EvalPaper) -> tuple[str, uuid.UUID]:
        async with limit:
            return paper.key, await _ensure_paper(owner_id, dataset, paper)

    return dict(await asyncio.gather(*(one(paper) for paper in papers)))


async def chunk_texts(paper_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[tuple[str, str]]]:
    """Per paper, its chunks as (id, text), to find which of them hold a piece of evidence."""
    texts: dict[uuid.UUID, list[tuple[str, str]]] = {paper_id: [] for paper_id in paper_ids}
    async with get_sessionmaker()() as db:
        rows = await db.execute(
            select(Chunk.paper_id, Chunk.id, Chunk.text)
            .where(Chunk.paper_id.in_(paper_ids), Chunk.kind != "reference")
            .order_by(Chunk.paper_id, Chunk.chunk_index)
        )
        for paper_id, chunk_id, text in rows:
            texts[paper_id].append((str(chunk_id), text))
    return texts


async def remove_all() -> int:
    """Deletes every evaluation account with its papers, index points and files."""
    async with get_sessionmaker()() as db:
        users = list(await db.scalars(select(User).where(User.email.endswith(f"@{EMAIL_DOMAIN}"))))
        for user in users:
            for paper_id in await db.scalars(select(Paper.id).where(Paper.owner_id == user.id)):
                await steps.remove(paper_id)
            await db.delete(user)
        await db.commit()
    return len(users)
