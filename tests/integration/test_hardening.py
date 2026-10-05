"""Failure paths, concurrent requests and hostile input."""

import asyncio

import pytest
from httpx import AsyncClient

from apps.api.main import app
from apps.api.routers import papers as papers_router
from scirag.auth import secrets
from scirag.config import get_settings
from tests.conftest import PASSWORD
from tests.integration.test_papers import stored_files, upload, upload_with
from tests.integration.test_providers import BEDROCK, ROUTER


async def test_same_file_uploaded_twice_at_once_is_stored_once(alice: AsyncClient):
    responses = await asyncio.gather(upload(alice), upload(alice))

    assert sorted(response.status_code for response in responses) == [202, 409]
    assert len(stored_files()) == 1
    assert (await alice.get("/papers")).json()["total"] == 1


async def test_same_email_registered_twice_at_once_creates_one_account(anon: AsyncClient):
    credentials = {"email": "carol@example.com", "password": PASSWORD}

    responses = await asyncio.gather(
        anon.post("/auth/register", json=credentials),
        anon.post("/auth/register", json=credentials),
    )

    assert sorted(response.status_code for response in responses) == [201, 409]


async def test_no_file_is_left_when_saving_the_paper_fails(alice: AsyncClient, monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(papers_router.papers_repo, "create", fail)

    with pytest.raises(RuntimeError):
        await upload(alice)

    assert stored_files() == []


async def test_authors_edited_twice_at_once_end_with_one_list(alice: AsyncClient):
    paper_id = await upload_with(alice, "one", title="One")
    url = f"/papers/{paper_id}"

    responses = await asyncio.gather(
        alice.patch(url, json={"authors": ["A"]}), alice.patch(url, json={"authors": ["B"]})
    )

    assert [response.status_code for response in responses] == [200, 200]
    assert (await alice.get(url)).json()["authors"] in (["A"], ["B"])
    assert (await alice.get("/papers", params={"sort": "author"})).status_code == 200


async def test_an_oversized_body_is_refused_before_it_is_read(anon: AsyncClient):
    limit_bytes = get_settings().max_upload_mb * 1024 * 1024

    response = await upload(anon, b"%PDF-" + b"0" * (limit_bytes * 3))

    # 413 rather than 401: the body was refused on its declared length alone.
    assert response.status_code == 413


async def test_a_pdf_sent_with_a_generic_content_type_is_accepted(alice: AsyncClient):
    response = await upload(alice, content_type="application/octet-stream")
    assert response.status_code == 202


@pytest.mark.parametrize(
    "changes",
    [
        {"authors": ["x" * 256]},
        {"authors": ["nul\x00inside"]},
        {"title": "nul\x00inside"},
        {"title": "   "},
        {"doi": "nul\x00inside"},
    ],
)
async def test_edit_rejects_text_the_database_cannot_store(alice: AsyncClient, changes: dict):
    paper_id = (await upload(alice)).json()["id"]
    assert (await alice.patch(f"/papers/{paper_id}", json=changes)).status_code == 422


@pytest.mark.parametrize(
    "params", [{"page": 10**30}, {"q": "nul\x00"}, {"author": "nul\x00"}, {"year": 10**30}]
)
async def test_list_rejects_values_the_database_cannot_take(alice: AsyncClient, params: dict):
    assert (await alice.get("/papers", params=params)).status_code == 422


async def test_a_file_name_with_a_nul_character_is_accepted(alice: AsyncClient):
    response = await upload(alice, filename="pa\x00per.pdf")
    assert response.status_code == 202
    assert "\x00" not in response.json()["original_filename"]


async def test_author_filter_does_not_reach_other_accounts(alice: AsyncClient, bob: AsyncClient):
    await upload_with(alice, "one", authors=["Shared Name"])
    assert (await bob.get("/papers", params={"author": "shared"})).json()["total"] == 0


async def test_total_counts_every_match_not_just_the_page(alice: AsyncClient):
    for number in range(3):
        await upload_with(alice, f"match {number}", year=2020)
    await upload_with(alice, "other", year=1999)

    page = (await alice.get("/papers", params={"year": 2020, "page_size": 2})).json()

    assert page["total"] == 3
    assert len(page["items"]) == 2


async def test_a_rejected_request_does_not_echo_the_secrets_it_carried(anon, alice):
    incomplete = {key: value for key, value in BEDROCK.items() if key != "region"}
    connection = await alice.post("/settings/providers", json=incomplete)
    register = await anon.post("/auth/register", json={"password": PASSWORD})

    assert connection.status_code == register.status_code == 422
    assert BEDROCK["secret_access_key"] not in connection.text
    assert PASSWORD not in register.text
    assert connection.json()["detail"][0]["loc"] == ["body", "bedrock", "region"]


async def test_a_base_url_with_credentials_in_it_is_rejected(alice: AsyncClient):
    payload = {**ROUTER, "base_url": "https://user:hunter2@router.example.com/v1"}
    assert (await alice.post("/settings/providers", json=payload)).status_code == 422


async def test_the_session_cookie_is_marked_secure_when_configured(anon, monkeypatch):
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    response = await anon.post(
        "/auth/register", json={"email": "carol@example.com", "password": PASSWORD}
    )
    assert "secure" in response.headers["set-cookie"].lower()


async def test_the_api_refuses_to_start_with_an_invalid_secrets_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "secrets_key", "not-a-key")
    secrets.get_fernet.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="SECRETS_KEY"):
            async with app.router.lifespan_context(app):
                pass
    finally:
        secrets.get_fernet.cache_clear()
