import hashlib
import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Annotated, BinaryIO

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from apps.api.deps import CurrentUser, Db, Storage
from apps.api.schemas.papers import (
    ChunkOut,
    ChunkPage,
    IngestionRunOut,
    PaperDetail,
    PaperOut,
    PaperPage,
    PaperUpdate,
    ReindexOut,
    SectionOut,
)
from apps.api.schemas.text import Text
from scientrag.config import get_settings
from scientrag.db.models import Paper, PaperStatus, User
from scientrag.db.repositories import ingestion as ingestion_repo
from scientrag.db.repositories import papers as papers_repo
from scientrag.db.repositories import provider_connections as connections_repo
from scientrag.db.repositories.papers import SortField, SortOrder
from scientrag.ingestion import queue
from scientrag.providers.defaults import models_for

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/papers", tags=["papers"])

PDF_MAGIC = b"%PDF-"
CHUNK_BYTES = 1024 * 1024


class UploadTooLarge(Exception):
    pass


def _too_large(limit_mb: int) -> HTTPException:
    return HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE, f"The file is larger than the {limit_mb} MB limit"
    )


def _duplicate(existing: Paper) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "You already uploaded this file",
            "code": "duplicate_paper",
            "paper_id": str(existing.id),
            "title": existing.title,
        },
    )


async def _get_or_404(
    db: Db, owner_id: uuid.UUID, paper_id: uuid.UUID, *, for_update: bool = False
) -> Paper:
    paper = await papers_repo.get(db, owner_id, paper_id, for_update=for_update)
    if paper is None:
        # Also the answer for someone else's paper: 404, so its existence is not revealed.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper not found")
    return paper


async def _current_embedding_model(db: Db, user: User) -> str | None:
    """The embedding model of the connection the account uses now, if it has one."""
    if user.active_connection_id is None:
        return None
    connection = await connections_repo.get(db, user.id, user.active_connection_id)
    if connection is None:
        return None
    return models_for(connection.kind, connection.config.get("models", {})).get("embedding")


def _out(paper: Paper, embedding_model: str | None) -> PaperOut:
    out = PaperOut.model_validate(paper)
    out.needs_reindex = (
        paper.status == PaperStatus.READY
        and embedding_model is not None
        and paper.embedding_model != embedding_model
    )
    return out


async def _queue_ingest(paper_id: uuid.UUID, first_step: str = "parse") -> bool:
    """False if the paper is already waiting or being processed."""
    try:
        return await queue.enqueue_ingest(paper_id, first_step)
    except Exception:
        # The paper is saved; it stays UPLOADED and can be started again with reingest.
        logger.exception("could not queue paper %s", paper_id)
        return False


def _queue_unavailable() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE, "The processing queue is unavailable. Try again."
    )


def _sha256_within_limit(handle: BinaryIO, limit_bytes: int) -> str:
    """Hashes the whole upload. Raises UploadTooLarge as soon as it passes the limit."""
    digest = hashlib.sha256()
    total = 0
    handle.seek(0)
    while chunk := handle.read(CHUNK_BYTES):
        total += len(chunk)
        if total > limit_bytes:
            raise UploadTooLarge
        digest.update(chunk)
    return digest.hexdigest()


def _chunks(handle: BinaryIO) -> Iterator[bytes]:
    handle.seek(0)
    while chunk := handle.read(CHUNK_BYTES):
        yield chunk


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=PaperOut)
async def upload_paper(file: UploadFile, user: CurrentUser, db: Db, storage: Storage):
    # Read now: a rollback below expires the user object.
    owner_id = user.id
    limit_mb = get_settings().max_upload_mb
    # The declared content type is not checked: clients often send a generic one for a real PDF.
    if await file.read(len(PDF_MAGIC)) != PDF_MAGIC:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "The file is not a PDF")
    try:
        file_sha256 = await run_in_threadpool(
            _sha256_within_limit, file.file, limit_mb * 1024 * 1024
        )
    except UploadTooLarge:
        raise _too_large(limit_mb) from None

    existing = await papers_repo.get_by_sha256(db, owner_id, file_sha256)
    if existing is not None:
        return _duplicate(existing)

    # The key is built from an id generated here, never from the uploaded file name.
    paper_id = uuid.uuid7()
    storage_key = f"papers/{paper_id}/original.pdf"
    filename = PurePath((file.filename or "").replace("\x00", "")).name[:255] or "paper.pdf"
    await run_in_threadpool(storage.put, storage_key, _chunks(file.file))
    try:
        paper = await papers_repo.create(
            db,
            paper_id=paper_id,
            owner_id=owner_id,
            title=PurePath(filename).stem or "Untitled",
            original_filename=filename,
            file_sha256=file_sha256,
            storage_key=storage_key,
        )
        await db.commit()
    except BaseException as error:
        # No row was saved, so nothing would ever point at the stored file.
        await run_in_threadpool(storage.delete, storage_key)
        if isinstance(error, IntegrityError):
            # The same file was uploaded twice at once and the other request won.
            await db.rollback()
            existing = await papers_repo.get_by_sha256(db, owner_id, file_sha256)
            if existing is not None:
                return _duplicate(existing)
        raise
    await _queue_ingest(paper_id)
    return paper


@router.get("", response_model=PaperPage)
async def list_papers(
    user: CurrentUser,
    db: Db,
    q: Annotated[Text | None, Query(max_length=200)] = None,
    # May be given more than once: ?status=UPLOADED&status=PROCESSING.
    status_filter: Annotated[list[PaperStatus] | None, Query(alias="status")] = None,
    year: Annotated[int | None, Query(ge=1000, le=2100)] = None,
    author: Annotated[Text | None, Query(max_length=200)] = None,
    sort: SortField = "added",
    order: SortOrder = "desc",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = await papers_repo.list_papers(
        db,
        user.id,
        q=q,
        statuses=status_filter,
        year=year,
        author=author,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    model = await _current_embedding_model(db, user)
    return PaperPage(
        items=[_out(item, model) for item in items], total=total, page=page, page_size=page_size
    )


@router.post("/reindex", status_code=status.HTTP_202_ACCEPTED, response_model=ReindexOut)
async def reindex_papers(user: CurrentUser, db: Db):
    """Embeds and indexes again, with the connection in use now, every paper that was
    indexed with another embedding model. The PDFs are not parsed again."""
    model = await _current_embedding_model(db, user)
    if model is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Choose a model connection with an embedding model first"
        )
    queued = 0
    for paper_id in await ingestion_repo.papers_needing_reindex(db, user.id, model):
        queued += await _queue_ingest(paper_id, "embed")
    return ReindexOut(queued=queued)


@router.get("/{paper_id}", response_model=PaperDetail)
async def get_paper(paper_id: uuid.UUID, user: CurrentUser, db: Db):
    paper = await _get_or_404(db, user.id, paper_id)
    out = PaperDetail.model_validate(_out(paper, await _current_embedding_model(db, user)))
    out.summary = await ingestion_repo.summary(db, paper_id)
    return out


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_paper(paper_id: uuid.UUID, user: CurrentUser, db: Db) -> None:
    """The paper disappears at once; the worker then removes its file, chunks and index points."""
    paper = await _get_or_404(db, user.id, paper_id, for_update=True)
    # Queued before the paper is hidden: a paper that is hidden but never cleaned up
    # would keep its file and index points for good. The worker waits on the row lock.
    try:
        await queue.enqueue_delete(paper_id)
    except Exception as error:
        logger.exception("could not queue the cleanup of paper %s", paper_id)
        raise _queue_unavailable() from error
    paper.deleted_at = datetime.now(UTC)
    await db.commit()


@router.post("/{paper_id}/reingest", status_code=status.HTTP_202_ACCEPTED, response_model=PaperOut)
async def reingest_paper(paper_id: uuid.UUID, user: CurrentUser, db: Db):
    """Processes the paper again from the PDF: after a failure, or to pick up a better parser."""
    paper = await _get_or_404(db, user.id, paper_id)
    try:
        queued = await queue.enqueue_ingest(paper_id)
    except Exception as error:
        logger.exception("could not queue paper %s", paper_id)
        raise _queue_unavailable() from error
    if not queued:
        raise HTTPException(status.HTTP_409_CONFLICT, "The paper is already being processed")
    # Only from a finished state: the worker may already have moved it to PROCESSING.
    await db.execute(
        update(Paper)
        .where(Paper.id == paper_id, Paper.status.in_([PaperStatus.READY, PaperStatus.FAILED]))
        .values(status=PaperStatus.UPLOADED, processing_step=None, error_code=None, error=None)
    )
    await db.commit()
    await db.refresh(paper)
    return _out(paper, None)


@router.get("/{paper_id}/sections", response_model=list[SectionOut])
async def list_sections(paper_id: uuid.UUID, user: CurrentUser, db: Db):
    """The paper's outline in reading order. parent_id gives the nesting."""
    await _get_or_404(db, user.id, paper_id)
    return await ingestion_repo.sections(db, paper_id)


@router.get("/{paper_id}/ingestion", response_model=list[IngestionRunOut])
async def list_ingestion_runs(paper_id: uuid.UUID, user: CurrentUser, db: Db):
    await _get_or_404(db, user.id, paper_id)
    return await ingestion_repo.runs(db, paper_id)


@router.get("/{paper_id}/chunks", response_model=ChunkPage)
async def list_chunks(
    paper_id: uuid.UUID,
    user: CurrentUser,
    db: Db,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
):
    await _get_or_404(db, user.id, paper_id)
    items, total = await ingestion_repo.chunks(db, paper_id, page=page, page_size=page_size)
    return ChunkPage(
        items=[ChunkOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{paper_id}", response_model=PaperOut)
async def update_paper(paper_id: uuid.UUID, changes: PaperUpdate, user: CurrentUser, db: Db):
    paper = await _get_or_404(db, user.id, paper_id, for_update=True)
    sent = changes.model_fields_set
    if "title" in sent:
        if changes.title is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "title cannot be null")
        paper.title = changes.title
    if "year" in sent:
        paper.year = changes.year
    if "doi" in sent:
        paper.doi = changes.doi.strip() or None if changes.doi else None
    if "authors" in sent:
        await papers_repo.replace_authors(db, paper, changes.authors or [])
    await db.commit()
    await db.refresh(paper)
    return _out(paper, await _current_embedding_model(db, user))


def _read_and_close(handle: BinaryIO) -> Iterator[bytes]:
    with handle:
        while chunk := handle.read(CHUNK_BYTES):
            yield chunk


@router.get("/{paper_id}/file")
async def download_paper_file(paper_id: uuid.UUID, user: CurrentUser, db: Db, storage: Storage):
    paper = await _get_or_404(db, user.id, paper_id)
    try:
        handle = await run_in_threadpool(storage.open, paper.storage_key)
    except FileNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "The file for this paper is missing"
        ) from error
    return StreamingResponse(
        _read_and_close(handle),
        media_type="application/pdf",
        # Named after the id, not the user's file name, which is untrusted text.
        headers={
            "Content-Disposition": f'inline; filename="{paper.id}.pdf"',
            # Only the first bytes were checked on upload; the browser must not guess another type.
            "X-Content-Type-Options": "nosniff",
        },
    )
