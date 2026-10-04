"""Model-provider connections of the signed-in account. Nothing here is shared between accounts."""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status

from apps.api.deps import CurrentUser, Db
from apps.api.schemas.auth import UserOut
from apps.api.schemas.providers import (
    ActiveConnectionChoice,
    BedrockCreate,
    ConnectionCreate,
    ConnectionOut,
    ConnectionUpdate,
    GeminiCreate,
)
from scientrag.auth.secrets import encrypt_secret
from scientrag.db.models import ProviderConnection
from scientrag.db.repositories import provider_connections as connections_repo

router = APIRouter(prefix="/settings", tags=["settings"])

CREDENTIAL_FIELDS = ("api_key", "access_key_id", "secret_access_key")


def _split(payload: ConnectionCreate) -> tuple[dict[str, Any], dict[str, str], str]:
    """Separates a create request into (public config, secret to encrypt, last 4 characters)."""
    config: dict[str, Any] = {"models": payload.models.model_dump(exclude_none=True)}
    if isinstance(payload, GeminiCreate):
        return config, {"api_key": payload.api_key}, payload.api_key[-4:]
    if isinstance(payload, BedrockCreate):
        config["region"] = payload.region
        secret = {
            "access_key_id": payload.access_key_id,
            "secret_access_key": payload.secret_access_key,
        }
        # The access key id identifies the credential and is not itself secret.
        return config, secret, payload.access_key_id[-4:]
    config["base_url"] = str(payload.base_url)
    return config, {"api_key": payload.api_key}, payload.api_key[-4:]


def _replace_credentials(connection: ProviderConnection, changes: ConnectionUpdate) -> None:
    """Swaps in the credentials sent, if any. They must be exactly those of the kind."""
    sent = {name for name in CREDENTIAL_FIELDS if getattr(changes, name) is not None}
    if not sent:
        return
    expected = (
        {"access_key_id", "secret_access_key"} if connection.kind == "bedrock" else {"api_key"}
    )
    if sent != expected:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"To replace the credentials of a {connection.kind} connection, "
            f"send exactly: {', '.join(sorted(expected))}",
        )
    connection.secret_encrypted = encrypt_secret({name: getattr(changes, name) for name in sent})
    connection.secret_last4 = (changes.access_key_id or changes.api_key)[-4:]


async def _get_or_404(db: Db, user_id: uuid.UUID, connection_id: uuid.UUID) -> ProviderConnection:
    connection = await connections_repo.get(db, user_id, connection_id)
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    return connection


@router.get("/providers", response_model=list[ConnectionOut])
async def list_connections(user: CurrentUser, db: Db):
    return await connections_repo.list_for_user(db, user.id)


@router.post("/providers", status_code=status.HTTP_201_CREATED, response_model=ConnectionOut)
async def create_connection(payload: ConnectionCreate, user: CurrentUser, db: Db):
    config, secret, last4 = _split(payload)
    connection = await connections_repo.create(
        db,
        user_id=user.id,
        kind=payload.kind,
        label=payload.label,
        config=config,
        secret_encrypted=encrypt_secret(secret),
        secret_last4=last4,
    )
    # An account's first connection is used right away; later ones wait to be chosen.
    if user.active_connection_id is None:
        user.active_connection_id = connection.id
    await db.commit()
    return connection


@router.patch("/providers/{connection_id}", response_model=ConnectionOut)
async def update_connection(
    connection_id: uuid.UUID, changes: ConnectionUpdate, user: CurrentUser, db: Db
):
    connection = await _get_or_404(db, user.id, connection_id)
    _replace_credentials(connection, changes)
    if changes.label is not None:
        connection.label = changes.label
    if changes.models is not None:
        # Assign a new dict: SQLAlchemy does not see in-place edits of a JSONB value.
        connection.config = {
            **connection.config,
            "models": changes.models.model_dump(exclude_none=True),
        }
    await db.commit()
    await db.refresh(connection)
    return connection


@router.delete("/providers/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(connection_id: uuid.UUID, user: CurrentUser, db: Db) -> None:
    connection = await _get_or_404(db, user.id, connection_id)
    # If this was the account's active connection, the foreign key resets that choice to null.
    await db.delete(connection)
    await db.commit()


@router.put("/active-connection", response_model=UserOut)
async def choose_active_connection(choice: ActiveConnectionChoice, user: CurrentUser, db: Db):
    """Picks the one connection the account uses for every model call. null clears the choice."""
    if choice.connection_id is not None:
        await _get_or_404(db, user.id, choice.connection_id)
    user.active_connection_id = choice.connection_id
    await db.commit()
    return user
