import pytest

from scientrag.ingestion.errors import PaperGone, PermanentIngestionError
from scientrag.ingestion.workflow import failure_of, should_retry
from scientrag.providers.errors import ProviderError, from_aws, from_http


@pytest.mark.parametrize(
    ("status", "message", "code"),
    [
        (401, "Incorrect API key provided", "invalid_key"),
        (403, "Permission denied", "invalid_key"),
        (400, "API key not valid. Please pass a valid API key.", "invalid_key"),
        (404, "models/nope is not found for API version v1beta", "model_not_found"),
        (400, "The model `nope` does not exist (model_not_found)", "model_not_found"),
        (402, "Payment required", "quota_exceeded"),
        (429, "You exceeded your current quota (insufficient_quota)", "quota_exceeded"),
        (429, "Quota exceeded for metric: GenerateRequestsPerDayPerProject", "quota_exceeded"),
        (429, "Resource has been exhausted, try again later", "rate_limited"),
        # Gemini words its per-minute limit like a billing problem; it still clears by waiting.
        (
            429,
            "You exceeded your current quota, please check your plan and billing details",
            "rate_limited",
        ),
        (500, "Internal error", "provider_unreachable"),
        (503, None, "provider_unreachable"),
        (400, "Invalid JSON payload", "provider_rejected"),
    ],
)
def test_http_errors_map_to_codes(status: int, message: str | None, code: str):
    assert from_http(status, message).code == code


@pytest.mark.parametrize(
    ("aws_code", "message", "code"),
    [
        ("UnrecognizedClientException", "The security token is invalid", "invalid_key"),
        ("ThrottlingException", "Too many requests", "rate_limited"),
        ("ResourceNotFoundException", "Could not resolve the foundation model", "model_not_found"),
        ("AccessDeniedException", "You don't have access to the model", "model_not_found"),
        ("AccessDeniedException", "User is not authorized", "invalid_key"),
        ("ValidationException", "The provided model identifier is invalid", "model_not_found"),
        ("ValidationException", "Malformed input request", "provider_rejected"),
        ("ServiceUnavailableException", None, "provider_unreachable"),
    ],
)
def test_aws_errors_map_to_codes(aws_code: str, message: str | None, code: str):
    assert from_aws(aws_code, message).code == code


def test_only_passing_failures_are_retryable():
    assert from_http(429, "slow down", retry_after=7).retry_after == 7
    retryable = {code for code in ("rate_limited", "provider_unreachable")}
    for code in (
        "invalid_key",
        "quota_exceeded",
        "rate_limited",
        "model_not_found",
        "provider_unreachable",
        "capability_missing",
        "provider_rejected",
        "provider_not_configured",
    ):
        assert ProviderError(code).retryable == (code in retryable)


def test_the_provider_message_is_shortened_to_one_line():
    error = from_http(400, "line one\n\n   line two " + "x" * 500)
    assert "\n" not in str(error)
    assert len(error.detail) == 300


def test_an_ingestion_step_retries_only_what_can_pass_on_its_own():
    assert should_retry(ProviderError("rate_limited"))
    assert should_retry(ProviderError("provider_unreachable"))
    assert should_retry(ConnectionError("database went away"))
    assert not should_retry(ProviderError("invalid_key"))
    assert not should_retry(ProviderError("provider_not_configured"))
    assert not should_retry(PermanentIngestionError("scanned_pdf", "no text"))
    assert not should_retry(PaperGone())


def test_a_failure_becomes_a_code_and_a_readable_message():
    assert failure_of(PermanentIngestionError("scanned_pdf", "No text.")) == (
        "scanned_pdf",
        "No text.",
    )
    assert failure_of(ProviderError("invalid_key"))[0] == "invalid_key"
    code, message = failure_of(RuntimeError("secret internals"))
    assert code == "temporary_failure"
    assert "secret internals" not in message
