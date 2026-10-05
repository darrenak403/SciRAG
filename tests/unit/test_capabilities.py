from collections.abc import AsyncIterator

import pytest

from scirag.providers.capabilities import check_provider
from scirag.providers.errors import ProviderError


class FakeProvider:
    """Answers like a working provider, except for what `broken` names."""

    def __init__(self, broken: str | None = None, error: ProviderError | None = None) -> None:
        self.broken = broken
        self.error = error or ProviderError("capability_missing")
        self.calls: list[str] = []
        self.usage = []

    def _maybe_fail(self, capability: str) -> None:
        self.calls.append(capability)
        if self.broken in (capability, "everything"):
            raise self.error

    async def complete(self, messages, *, role, max_tokens, system=None, json_output=False) -> str:
        self._maybe_fail("json" if json_output else "chat")
        return "[1, 2]" if json_output else "ready"

    async def stream(self, messages, *, role, max_tokens, system=None) -> AsyncIterator[str]:
        self._maybe_fail("stream")
        yield "ready"

    async def embed_query(self, text: str) -> list[float]:
        self._maybe_fail("embed")
        return [0.0] * 8


def results(report: dict) -> dict[str, bool]:
    return {check["check"]: check["ok"] for check in report["checks"]}


async def test_a_working_provider_passes_every_check():
    report = await check_provider(FakeProvider())

    assert results(report) == {
        "authentication": True,
        "chat": True,
        "streaming": True,
        "structured_output": True,
        "embeddings": True,
    }
    assert report["usable"] is True
    assert report["rerank_disabled"] is False
    assert report["checks"][-1]["message"] == "8 dimensions"


@pytest.mark.parametrize(
    ("broken", "failed_check"),
    [("chat", "chat"), ("stream", "streaming"), ("embed", "embeddings")],
)
async def test_a_missing_required_capability_makes_the_connection_unusable(broken, failed_check):
    report = await check_provider(FakeProvider(broken))

    assert results(report)[failed_check] is False
    assert results(report)["authentication"] is True
    assert report["usable"] is False
    failed = next(check for check in report["checks"] if check["check"] == failed_check)
    assert failed["error_code"] == "capability_missing"


async def test_without_json_output_the_connection_works_but_reranking_is_off():
    report = await check_provider(FakeProvider("json"))

    assert results(report)["structured_output"] is False
    assert report["usable"] is True
    assert report["rerank_disabled"] is True


async def test_a_rejected_key_fails_everything_after_one_call():
    provider = FakeProvider("everything", ProviderError("invalid_key"))

    report = await check_provider(provider)

    assert not any(results(report).values())
    assert {check["error_code"] for check in report["checks"]} == {"invalid_key"}
    assert report["usable"] is False
    # The other checks are not attempted with a key the provider already refused.
    assert provider.calls == ["chat"]
