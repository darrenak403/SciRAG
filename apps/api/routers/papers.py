import hashlib
import uuid
from collections.abc import Iterator
from pathlib import PurePath
from typing import Annotated, BinaryIO

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.exc import IntegrityError

from apps.api.deps import CurrentUser, Db, Storage
from apps.api.schemas.papers import PaperOut, PaperPage, PaperUpdate
from apps.api.schemas.text import Text
from scientrag.config import get_settings
from scientrag.db.models import Paper, PaperStatus
from scientrag.db.repositories import papers as papers_repo
from scientrag.db.repositories.papers import SortField, SortOrder

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
    return paper


@router.get("", response_model=PaperPage)
async def list_papers(
    user: CurrentUser,
    db: Db,
    q: Annotated[Text | None, Query(max_length=200)] = None,
    status_filter: Annotated[PaperStatus | None, Query(alias="status")] = None,
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
        status=status_filter,
        year=year,
        author=author,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    return PaperPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{paper_id}", response_model=PaperOut)
async def get_paper(paper_id: uuid.UUID, user: CurrentUser, db: Db):
    return await _get_or_404(db, user.id, paper_id)


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
    return paper


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
