from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from scientrag.auth import login_limiter
from scientrag.auth.sessions import COOKIE_NAME, hash_token
from scientrag.config import get_settings
from scientrag.db.models import Session, User
from tests.conftest import PASSWORD

ALICE = {"email": "alice@example.com", "password": PASSWORD}


async def test_register_signs_the_user_in(anon: AsyncClient):
    response = await anon.post("/auth/register", json=ALICE)

    assert response.status_code == 201
    assert response.json()["email"] == "alice@example.com"
    assert "password" not in response.text
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie

    me = await anon.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


async def test_password_is_stored_hashed(alice: AsyncClient, db: AsyncSession):
    user = await db.scalar(select(User))
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


async def test_session_token_is_stored_only_as_a_hash(alice: AsyncClient, db: AsyncSession):
    token = alice.cookies[COOKIE_NAME]
    stored = await db.scalar(select(Session.token_hash))
    assert stored == hash_token(token)
    assert stored != token


async def test_register_rejects_an_email_already_in_use(alice: AsyncClient, anon: AsyncClient):
    response = await anon.post(
        "/auth/register", json={"email": "Alice@Example.com", "password": PASSWORD}
    )
    assert response.status_code == 409


async def test_register_rejects_a_short_password(anon: AsyncClient):
    response = await anon.post(
        "/auth/register", json={"email": "alice@example.com", "password": "short"}
    )
    assert response.status_code == 422


async def test_register_can_be_closed(anon: AsyncClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_registration", False)
    response = await anon.post("/auth/register", json=ALICE)
    assert response.status_code == 403


async def test_login_with_the_right_password(alice: AsyncClient, anon: AsyncClient):
    response = await anon.post("/auth/login", json=ALICE)
    assert response.status_code == 200
    assert (await anon.get("/auth/me")).status_code == 200


async def test_login_gives_the_same_answer_for_wrong_password_and_unknown_email(
    alice: AsyncClient, anon: AsyncClient
):
    wrong_password = await anon.post(
        "/auth/login", json={"email": "alice@example.com", "password": "not the password"}
    )
    unknown_email = await anon.post(
        "/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_login_is_blocked_after_repeated_failures(alice: AsyncClient, anon: AsyncClient):
    wrong = {"email": "alice@example.com", "password": "not the password"}
    for _ in range(login_limiter.MAX_FAILURES):
        assert (await anon.post("/auth/login", json=wrong)).status_code == 401

    # Even the right password is refused while the block lasts.
    assert (await anon.post("/auth/login", json=ALICE)).status_code == 429


async def test_me_requires_a_session(anon: AsyncClient):
    assert (await anon.get("/auth/me")).status_code == 401
    anon.cookies.set(COOKIE_NAME, "made-up-token")
    assert (await anon.get("/auth/me")).status_code == 401


async def test_logout_ends_the_session_on_the_server(alice: AsyncClient, anon: AsyncClient):
    token = alice.cookies[COOKIE_NAME]
    assert (await alice.post("/auth/logout")).status_code == 204
    assert COOKIE_NAME not in alice.cookies

    # A copy of the old cookie no longer works either.
    anon.cookies.set(COOKIE_NAME, token)
    assert (await anon.get("/auth/me")).status_code == 401


async def test_an_expired_session_is_rejected(alice: AsyncClient, db: AsyncSession):
    await db.execute(text("UPDATE sessions SET expires_at = now() - interval '1 second'"))
    await db.commit()
    assert (await alice.get("/auth/me")).status_code == 401


async def test_health(anon: AsyncClient):
    response = await anon.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
