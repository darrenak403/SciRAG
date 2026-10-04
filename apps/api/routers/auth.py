import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError

from apps.api.deps import CurrentUser, Db
from apps.api.schemas.auth import Credentials, UserOut
from scientrag.auth import login_limiter
from scientrag.auth.passwords import DUMMY_HASH, hash_password, verify_password
from scientrag.auth.sessions import COOKIE_NAME, hash_token, new_token
from scientrag.config import get_settings
from scientrag.db.repositories import sessions as sessions_repo
from scientrag.db.repositories import users as users_repo

router = APIRouter(prefix="/auth", tags=["auth"])


async def _start_session(db: Db, response: Response, user_id: uuid.UUID) -> None:
    """Creates a session row and sets its token as the session cookie."""
    settings = get_settings()
    lifetime = timedelta(days=settings.session_ttl_days)
    token = new_token()
    await sessions_repo.delete_expired(db, user_id)
    await sessions_repo.create(db, user_id, hash_token(token), datetime.now(UTC) + lifetime)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
async def register(credentials: Credentials, response: Response, db: Db):
    if not get_settings().allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is closed")
    if await users_repo.get_by_email(db, credentials.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    # Argon2 is deliberately slow: off the event loop, so other requests keep being served.
    password_hash = await run_in_threadpool(hash_password, credentials.password)
    try:
        user = await users_repo.create(db, credentials.email, password_hash)
    except IntegrityError as error:  # two registrations for the same email at once
        raise HTTPException(
            status.HTTP_409_CONFLICT, "An account with this email already exists"
        ) from error
    await _start_session(db, response, user.id)
    await db.commit()
    return user


@router.post("/login", response_model=UserOut)
async def login(credentials: Credentials, request: Request, response: Response, db: Db):
    ip = request.client.host if request.client else "unknown"
    if login_limiter.is_blocked(ip, credentials.email):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed sign-in attempts. Try again later."
        )

    # Counted before the slow checks and cleared on success, so attempts sent at
    # the same moment cannot all slip past the limit.
    login_limiter.record_failure(ip, credentials.email)

    user = await users_repo.get_by_email(db, credentials.email)
    # Always verify something, so a missing account is not faster than a wrong password.
    password_ok = await run_in_threadpool(
        verify_password, user.password_hash if user else DUMMY_HASH, credentials.password
    )
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")

    login_limiter.clear(ip, credentials.email)
    await _start_session(db, response, user.id)
    await db.commit()
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response, db: Db, token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None
) -> None:
    if token:
        await sessions_repo.delete_by_token(db, hash_token(token))
        await db.commit()
    response.delete_cookie(COOKIE_NAME)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
