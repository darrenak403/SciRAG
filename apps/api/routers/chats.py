import dataclasses
import logging
import uuid
from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from apps.api.deps import CurrentUser, Db
from apps.api.schemas.chats import (
    ChatCreate,
    ChatOut,
    ChatUpdate,
    MessageOut,
    QuestionIn,
    RetrievalOut,
    SourceOut,
)
from apps.api.sse import EventStream, event
from scirag.access.readable_papers import readable_collection_papers, readable_papers
from scirag.db.engine import get_sessionmaker
from scirag.db.models import ChatMessage, ChatSession, MessageSource, ProviderConnection
from scirag.db.repositories import chats as chats_repo
from scirag.db.repositories import collections as collections_repo
from scirag.providers.base import Message
from scirag.providers.errors import ProviderError
from scirag.providers.resolve import active_connection
from scirag.rag import citation, engine
from scirag.rag.analyzer import HISTORY_MESSAGES
from scirag.rag.engine import AskedMode
from scirag.rag.types import Delta, Done, Sources, Status, Table

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chats", tags=["chats"])

TITLE_CHARS = 80


async def _outs(db: Db, user_id: uuid.UUID, sessions: Sequence[ChatSession]) -> list[ChatOut]:
    """The chats as the API shows them. A scope lists only papers that still exist;
    a chat on a collection lists what the collection holds now."""
    named = {paper_id for session in sessions for paper_id in chats_repo.paper_ids_of(session)}
    live = {paper.id for paper in await readable_papers(db, user_id, named, ready_only=False)}
    collections = {chats_repo.collection_id_of(session) for session in sessions} - {None}
    held = await collections_repo.paper_ids(db, user_id, list(collections))
    kept = {collection.id for collection in await collections_repo.list_all(db, user_id)}
    outs = []
    for session in sessions:
        collection_id = chats_repo.collection_id_of(session)
        if collection_id is not None:
            paper_ids = held[collection_id]
        else:
            paper_ids = [pid for pid in chats_repo.paper_ids_of(session) if pid in live]
        outs.append(
            ChatOut(
                id=session.id,
                title=session.title,
                paper_ids=paper_ids,
                # A collection that was deleted leaves the chat with nothing to search.
                collection_id=collection_id if collection_id in kept else None,
                source_count=len(paper_ids),
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
        )
    return outs


async def _out(db: Db, session: ChatSession) -> ChatOut:
    return (await _outs(db, session.user_id, [session]))[0]


async def _get_or_404(db: Db, user_id: uuid.UUID, chat_id: uuid.UUID) -> ChatSession:
    session = await chats_repo.get(db, user_id, chat_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    return session


async def _check_scope(db: Db, user_id: uuid.UUID, paper_ids: list[uuid.UUID]) -> None:
    """Refuses a scope that names a paper the account cannot read."""
    wanted = set(paper_ids)
    readable = await readable_papers(db, user_id, wanted, ready_only=False)
    if len(readable) != len(wanted):
        # The same answer for a paper that does not exist and for someone else's.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"code": "paper_not_found", "message": "The scope names a paper you do not have."},
        )


async def _scope(
    db: Db, user_id: uuid.UUID, paper_ids: list[uuid.UUID], collection_id: uuid.UUID | None
) -> dict:
    """The scope to store, once it is sure the account has what it names."""
    if collection_id is None:
        await _check_scope(db, user_id, paper_ids)
        return chats_repo.scope_of(paper_ids)
    if await collections_repo.get(db, user_id, collection_id) is None:
        # The same answer for a collection that does not exist and for someone else's.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"code": "collection_not_found", "message": "You do not have this collection."},
        )
    return chats_repo.collection_scope(collection_id)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ChatOut)
async def create_chat(payload: ChatCreate, user: CurrentUser, db: Db):
    scope = await _scope(db, user.id, payload.paper_ids, payload.collection_id)
    session = await chats_repo.create(db, user.id, title=payload.title, scope=scope)
    await db.commit()
    return await _out(db, session)


@router.get("", response_model=list[ChatOut])
async def list_chats(
    user: CurrentUser,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    collection_id: uuid.UUID | None = None,
):
    """The account's chats, the one used last first; collection_id keeps those on it."""
    found = await chats_repo.list_recent(db, user.id, limit=limit, collection_id=collection_id)
    return await _outs(db, user.id, found)


@router.get("/messages/{message_id}/retrieval", response_model=RetrievalOut)
async def get_retrieval(message_id: uuid.UUID, user: CurrentUser, db: Db):
    """How the passages of an answer were found: the search query, candidates and ranking."""
    message = await chats_repo.get_message(db, user.id, message_id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    return RetrievalOut(
        message_id=message.id, trace_id=message.trace_id, retrieval=message.retrieval
    )


@router.get("/{chat_id}", response_model=ChatOut)
async def get_chat(chat_id: uuid.UUID, user: CurrentUser, db: Db):
    return await _out(db, await _get_or_404(db, user.id, chat_id))


@router.patch("/{chat_id}", response_model=ChatOut)
async def update_chat(chat_id: uuid.UUID, changes: ChatUpdate, user: CurrentUser, db: Db):
    session = await _get_or_404(db, user.id, chat_id)
    if changes.title is not None:
        session.title = changes.title
    if changes.collection_id is not None:
        session.scope = await _scope(db, user.id, [], changes.collection_id)
    elif changes.paper_ids is not None:
        session.scope = await _scope(db, user.id, changes.paper_ids, None)
    await db.commit()
    await db.refresh(session)
    return await _out(db, session)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: uuid.UUID, user: CurrentUser, db: Db) -> None:
    await db.delete(await _get_or_404(db, user.id, chat_id))
    await db.commit()


@router.get("/{chat_id}/messages", response_model=list[MessageOut])
async def list_messages(chat_id: uuid.UUID, user: CurrentUser, db: Db):
    session = await _get_or_404(db, user.id, chat_id)
    messages = await chats_repo.messages(db, session.id)
    cited = await chats_repo.sources(db, [message.id for message in messages])
    return [
        MessageOut(
            id=message.id,
            role=message.role,
            content=message.content,
            citations=[SourceOut.model_validate(source) for source in cited.get(message.id, [])],
            mode=message.mode,
            table=message.table,
            notice=(message.retrieval or {}).get("notice"),
            created_at=message.created_at,
        )
        for message in messages
    ]


async def _save(user_id: uuid.UUID, chat_id: uuid.UUID, question: str, done: Done) -> uuid.UUID:
    """Stores the question and its answer together. Returns the id of the answer."""
    async with get_sessionmaker()() as db:
        session = await chats_repo.get(db, user_id, chat_id, for_update=True)
        if session is None:
            raise LookupError("the chat was deleted while it was being answered")
        db.add(ChatMessage(session_id=chat_id, role="user", content=question))
        # Flushed on its own so the question gets the earlier id.
        await db.flush()
        reply = ChatMessage(
            session_id=chat_id,
            role="assistant",
            content=done.text,
            trace_id=done.trace_id,
            retrieval={"outcome": done.outcome, "notice": done.notice, **done.retrieval},
            mode=done.mode,
            table=done.table,
        )
        db.add(reply)
        await db.flush()
        db.add_all(
            MessageSource(message_id=reply.id, **dataclasses.asdict(source))
            for source in done.citations
        )
        if session.title is None:
            session.title = question[:TITLE_CHARS]
        await chats_repo.touch(db, session)
        await db.commit()
        return reply.id


async def _answer_events(
    connection: ProviderConnection,
    chat_id: uuid.UUID,
    question: str,
    paper_ids: list[uuid.UUID],
    history: list[Message],
    mode: AskedMode = "auto",
) -> AsyncGenerator[str]:
    """The answer as server-sent events. Nothing is stored unless it completes."""
    answer = engine.answer(connection, question, paper_ids=paper_ids, history=history, mode=mode)
    try:
        # Closed with this generator, so a reader who leaves ends the model call too.
        async with aclosing(answer):
            async for item in answer:
                if isinstance(item, Sources):
                    yield event("sources", [dataclasses.asdict(source) for source in item.sources])
                elif isinstance(item, Delta):
                    yield event("delta", {"text": item.text})
                elif isinstance(item, Status):
                    yield event("status", dataclasses.asdict(item))
                elif isinstance(item, Table):
                    yield event("table", item.table)
                else:
                    message_id = await _save(connection.user_id, chat_id, question, item)
                    yield event(
                        "done",
                        {
                            "message_id": message_id,
                            "text": item.text,
                            "citations": [source.marker for source in item.citations],
                            "outcome": item.outcome,
                            "mode": item.mode,
                            "table": item.table,
                            "notice": item.notice,
                        },
                    )
    except ProviderError as error:
        yield event("error", {"code": error.code, "message": str(error)})
    except Exception as error:
        # The type only: the message of an unexpected error may quote the question.
        logger.error("Answering a question failed: %s", type(error).__name__)
        yield event("error", {"code": "internal_error", "message": "Something went wrong."})


@router.post("/{chat_id}/messages")
async def ask(chat_id: uuid.UUID, payload: QuestionIn, user: CurrentUser, db: Db):
    """Answers a question from the papers in the chat's scope, as a stream of events:
    `sources`, then `delta` pieces, then `done` with the checked text, or `error`.
    An answer that takes a while reports `status` on the way, and a comparison
    sends its `table` before the text."""
    session = await _get_or_404(db, user.id, chat_id)
    try:
        connection = await active_connection(user.id)
    except ProviderError as error:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"code": error.code, "message": str(error)}
        ) from error
    history: list[Message] = [
        # Markers of an earlier answer name passages that are numbered anew for this one.
        {
            "role": message.role,
            "content": citation.without_markers(message.content)
            if message.role == "assistant"
            else message.content,
        }
        for message in await chats_repo.messages(db, session.id, last=HISTORY_MESSAGES)
    ]
    collection_id = chats_repo.collection_id_of(session)
    if collection_id is not None:
        paper_ids = await readable_collection_papers(db, user.id, collection_id)
    else:
        paper_ids = chats_repo.paper_ids_of(session)
    events = _answer_events(
        connection, session.id, payload.content, paper_ids, history, payload.mode
    )
    # The answer may stream for minutes; it must not keep this request's connection.
    await db.close()
    return EventStream(events)
