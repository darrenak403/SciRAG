from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scientrag.auth.secrets import decrypt_secret
from scientrag.db.models import ProviderConnection
from scientrag.providers.errors import ProviderError

# Made-up values in the shape of real credentials.
GEMINI_KEY = "test-gemini-key-0000-abcd"
GEMINI = {"kind": "gemini", "label": "My Gemini", "api_key": GEMINI_KEY}
BEDROCK = {
    "kind": "bedrock",
    "label": "Work AWS",
    "region": "us-east-1",
    "access_key_id": "TESTACCESSKEYID1234",
    "secret_access_key": "test-secret-access-key-wxyz",
}
ROUTER = {
    "kind": "openai_compatible",
    "label": "9router",
    "base_url": "https://router.example.com/v1",
    "api_key": "test-router-key-5678",
    "models": {"answer": "big-model", "fast": "small-model"},
}


async def create(client: AsyncClient, payload: dict) -> dict:
    response = await client.post("/settings/providers", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_the_key_is_encrypted_in_the_database_and_never_returned(
    alice: AsyncClient, db: AsyncSession
):
    response = await alice.post("/settings/providers", json=GEMINI)

    assert response.status_code == 201
    assert response.json()["secret_last4"] == "abcd"
    assert GEMINI_KEY not in response.text
    assert GEMINI_KEY not in (await alice.get("/settings/providers")).text

    row = await db.scalar(select(ProviderConnection))
    assert GEMINI_KEY not in row.secret_encrypted
    assert GEMINI_KEY not in str(row.config)
    assert decrypt_secret(row.secret_encrypted) == {"api_key": GEMINI_KEY}


async def test_each_kind_keeps_its_own_settings(alice: AsyncClient, db: AsyncSession):
    gemini = await create(alice, GEMINI)
    bedrock = await create(alice, BEDROCK)
    router = await create(alice, ROUTER)

    assert gemini["config"] == {"models": {}}
    assert bedrock["config"] == {"models": {}, "region": "us-east-1"}
    assert router["config"] == {
        "models": {"answer": "big-model", "fast": "small-model"},
        "base_url": "https://router.example.com/v1",
    }
    listing = (await alice.get("/settings/providers")).json()
    assert [item["id"] for item in listing] == [gemini["id"], bedrock["id"], router["id"]]

    # Both halves of the AWS credential are encrypted; the secret half is in no response.
    assert BEDROCK["secret_access_key"] not in str(listing)
    row = await db.scalar(select(ProviderConnection).where(ProviderConnection.kind == "bedrock"))
    assert decrypt_secret(row.secret_encrypted) == {
        "access_key_id": BEDROCK["access_key_id"],
        "secret_access_key": BEDROCK["secret_access_key"],
    }


async def test_invalid_connections_are_rejected(alice: AsyncClient):
    async def status_of(payload: dict) -> int:
        return (await alice.post("/settings/providers", json=payload)).status_code

    assert await status_of({**GEMINI, "kind": "unknown"}) == 422
    assert await status_of({**GEMINI, "api_key": ""}) == 422
    assert await status_of({**BEDROCK, "region": "not a region"}) == 422
    # Only http and https endpoints are accepted.
    assert await status_of({**ROUTER, "base_url": "file:///etc/passwd"}) == 422
    assert await status_of({**ROUTER, "base_url": "ftp://router.example.com"}) == 422
    assert (await alice.get("/settings/providers")).json() == []


async def test_connections_require_a_session(anon: AsyncClient):
    assert (await anon.get("/settings/providers")).status_code == 401
    assert (await anon.post("/settings/providers", json=GEMINI)).status_code == 401


async def test_rename_and_change_models(alice: AsyncClient):
    connection = await create(alice, ROUTER)
    url = f"/settings/providers/{connection['id']}"

    renamed = (await alice.patch(url, json={"label": "Home router"})).json()
    assert renamed["label"] == "Home router"
    assert renamed["config"] == connection["config"]

    changed = (await alice.patch(url, json={"models": {"embedding": "embed-model"}})).json()
    assert changed["label"] == "Home router"
    assert changed["config"] == {
        "models": {"embedding": "embed-model"},
        "base_url": "https://router.example.com/v1",
    }


async def test_another_user_cannot_touch_the_connection(alice: AsyncClient, bob: AsyncClient):
    connection_id = (await create(alice, GEMINI))["id"]
    url = f"/settings/providers/{connection_id}"

    assert (await bob.get("/settings/providers")).json() == []
    assert (await bob.patch(url, json={"label": "stolen"})).status_code == 404
    assert (await bob.delete(url)).status_code == 404
    # Nor use it for their own account.
    choice = await bob.put("/settings/active-connection", json={"connection_id": connection_id})
    assert choice.status_code == 404
    assert (await bob.get("/auth/me")).json()["active_connection_id"] is None

    assert [item["label"] for item in (await alice.get("/settings/providers")).json()] == [
        "My Gemini"
    ]


async def test_the_first_connection_becomes_the_active_one(alice: AsyncClient):
    first = await create(alice, GEMINI)
    await create(alice, ROUTER)

    assert (await alice.get("/auth/me")).json()["active_connection_id"] == first["id"]


async def test_switch_and_clear_the_active_connection(alice: AsyncClient):
    await create(alice, GEMINI)
    router_id = (await create(alice, ROUTER))["id"]

    chosen = await alice.put("/settings/active-connection", json={"connection_id": router_id})
    assert chosen.status_code == 200
    assert (await alice.get("/auth/me")).json()["active_connection_id"] == router_id

    cleared = await alice.put("/settings/active-connection", json={"connection_id": None})
    assert cleared.json()["active_connection_id"] is None


async def test_deleting_the_chosen_connection_clears_the_choice(alice: AsyncClient):
    connection_id = (await create(alice, GEMINI))["id"]
    await alice.put("/settings/active-connection", json={"connection_id": connection_id})

    assert (await alice.delete(f"/settings/providers/{connection_id}")).status_code == 204

    assert (await alice.get("/settings/providers")).json() == []
    assert (await alice.get("/auth/me")).json()["active_connection_id"] is None


async def test_replace_the_key_of_a_connection(alice: AsyncClient, db: AsyncSession):
    connection = await create(alice, GEMINI)
    await alice.put("/settings/active-connection", json={"connection_id": connection["id"]})
    new_key = "test-gemini-key-1111-wxyz"

    response = await alice.patch(
        f"/settings/providers/{connection['id']}", json={"api_key": new_key}
    )

    assert response.status_code == 200
    assert new_key not in response.text
    changed = response.json()
    assert changed["secret_last4"] == "wxyz"
    assert changed["label"] == connection["label"]
    assert changed["config"] == connection["config"]
    # Same connection, so the account keeps using it.
    assert (await alice.get("/auth/me")).json()["active_connection_id"] == connection["id"]
    row = await db.scalar(select(ProviderConnection))
    assert decrypt_secret(row.secret_encrypted) == {"api_key": new_key}


async def test_replace_both_halves_of_a_bedrock_credential(alice: AsyncClient, db: AsyncSession):
    connection = await create(alice, BEDROCK)
    new = {"access_key_id": "TESTACCESSKEYID5678", "secret_access_key": "test-secret-key-new"}

    response = await alice.patch(f"/settings/providers/{connection['id']}", json=new)

    assert response.status_code == 200
    assert response.json()["secret_last4"] == "5678"
    row = await db.scalar(select(ProviderConnection))
    assert decrypt_secret(row.secret_encrypted) == new


async def test_credentials_of_the_wrong_kind_change_nothing(alice: AsyncClient, db: AsyncSession):
    gemini = await create(alice, GEMINI)
    bedrock = await create(alice, BEDROCK)

    async def patch(connection: dict, changes: dict) -> int:
        url = f"/settings/providers/{connection['id']}"
        return (await alice.patch(url, json=changes)).status_code

    assert await patch(bedrock, {"access_key_id": "TESTACCESSKEYID5678"}) == 422
    assert await patch(bedrock, {"api_key": "test-key-for-another-kind"}) == 422
    assert await patch(gemini, {"access_key_id": "A" * 20, "secret_access_key": "s" * 20}) == 422
    assert await patch(gemini, {"label": "Renamed", "access_key_id": "A" * 20}) == 422

    listing = (await alice.get("/settings/providers")).json()
    assert [item["secret_last4"] for item in listing] == ["abcd", "1234"]
    assert [item["label"] for item in listing] == ["My Gemini", "Work AWS"]
    row = await db.scalar(select(ProviderConnection).where(ProviderConnection.kind == "gemini"))
    assert decrypt_secret(row.secret_encrypted) == {"api_key": GEMINI_KEY}


async def test_a_new_connection_is_tested_and_the_result_is_shown(alice: AsyncClient):
    connection = await create(alice, GEMINI)

    assert connection["capabilities"]["usable"] is True
    assert (await alice.get("/settings/providers")).json()[0]["capabilities"]["usable"] is True


async def test_a_connection_that_fails_its_test_is_saved_but_not_used(
    alice: AsyncClient, connection_check: dict
):
    connection_check["usable"] = False
    broken = await create(alice, GEMINI)

    assert broken["capabilities"]["usable"] is False
    assert (await alice.get("/auth/me")).json()["active_connection_id"] is None
    choice = await alice.put("/settings/active-connection", json={"connection_id": broken["id"]})
    assert choice.status_code == 409
    assert choice.json()["detail"]["code"] == "connection_not_usable"

    # Fixed and tested again, it can be chosen.
    connection_check["usable"] = True
    tested = await alice.post(f"/settings/providers/{broken['id']}/test")
    assert tested.status_code == 200
    assert tested.json()["capabilities"]["usable"] is True
    choice = await alice.put("/settings/active-connection", json={"connection_id": broken["id"]})
    assert choice.status_code == 200


async def test_a_new_key_or_model_is_tested_again_but_a_new_label_is_not(
    alice: AsyncClient, connection_check: dict
):
    connection = await create(alice, GEMINI)
    url = f"/settings/providers/{connection['id']}"
    connection_check["usable"] = False

    assert (await alice.patch(url, json={"label": "Renamed"})).json()["capabilities"]["usable"]

    changed = await alice.patch(url, json={"models": {"fast": "another-model"}})
    assert changed.json()["capabilities"]["usable"] is False


async def test_listing_models_reports_a_provider_failure(alice: AsyncClient, monkeypatch):
    class Provider:
        usage: list = []

        async def list_models(self) -> list[str]:
            if failing:
                raise ProviderError("invalid_key")
            return ["model-b", "model-a"]

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("scientrag.providers.resolve.build_provider", lambda connection: Provider())
    connection = await create(alice, GEMINI)
    url = f"/settings/providers/{connection['id']}/models"

    failing = False
    assert (await alice.get(url)).json() == {"models": ["model-a", "model-b"]}

    failing = True
    response = await alice.get(url)
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "invalid_key"
    assert GEMINI_KEY not in response.text


async def test_another_user_cannot_test_or_list_models(alice: AsyncClient, bob: AsyncClient):
    connection_id = (await create(alice, GEMINI))["id"]

    assert (await bob.post(f"/settings/providers/{connection_id}/test")).status_code == 404
    assert (await bob.get(f"/settings/providers/{connection_id}/models")).status_code == 404
    assert (await bob.get("/settings/providers/usage")).json() == []
