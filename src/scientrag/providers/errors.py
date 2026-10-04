"""One error type for every model provider, with a fixed set of codes the UI can explain."""

import re
from typing import Literal

ErrorCode = Literal[
    "invalid_key",
    "quota_exceeded",
    "rate_limited",
    "model_not_found",
    "provider_unreachable",
    "capability_missing",
    # The provider refused the request for a reason none of the codes above covers.
    "provider_rejected",
    # The account has no usable connection chosen.
    "provider_not_configured",
]

# Worth trying again shortly; every other code needs the user to change something.
RETRYABLE: frozenset[str] = frozenset({"rate_limited", "provider_unreachable"})

MESSAGES: dict[str, str] = {
    "invalid_key": "The provider rejected the credentials.",
    "quota_exceeded": "The quota of this key is used up.",
    "rate_limited": "The provider is limiting requests for this key. Try again shortly.",
    "model_not_found": "The provider does not offer this model to this key.",
    "provider_unreachable": "The provider could not be reached.",
    "capability_missing": "The connection lacks something the system needs.",
    "provider_rejected": "The provider rejected the request.",
    "provider_not_configured": "No model provider is set up. Add one in Settings.",
}


class ProviderError(Exception):
    def __init__(
        self, code: ErrorCode, detail: str | None = None, *, retry_after: float | None = None
    ) -> None:
        self.code = code
        self.detail = detail
        self.retry_after = retry_after
        message = MESSAGES[code]
        super().__init__(f"{message} ({detail})" if detail else message)

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE


def _clip(text: str | None) -> str | None:
    """What a provider said, shortened to one line. Providers do not echo the key."""
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip()[:300] or None


def from_http(
    status: int, message: str | None, *, retry_after: float | None = None
) -> ProviderError:
    """Maps an HTTP error from Gemini or an OpenAI-compatible server to a code.

    message is the provider's own error text, already extracted from the body.
    """
    text = (message or "").lower()
    detail = _clip(message)
    if status in (401, 403) or "api key not valid" in text or "api_key_invalid" in text:
        return ProviderError("invalid_key", detail)
    if status == 404 or "model_not_found" in text or "is not found for api version" in text:
        return ProviderError("model_not_found", detail)
    if status == 402 or "insufficient_quota" in text:
        return ProviderError("quota_exceeded", detail)
    if status == 429:
        # A daily limit will not clear by waiting a few seconds. The wording alone does
        # not tell: Gemini mentions "quota" and "billing" for per-minute limits too.
        if "perday" in text.replace("_", "").replace(" ", ""):
            return ProviderError("quota_exceeded", detail)
        return ProviderError("rate_limited", detail, retry_after=retry_after)
    if status >= 500:
        return ProviderError("provider_unreachable", detail, retry_after=retry_after)
    return ProviderError("provider_rejected", detail)


# AWS error codes, as botocore reports them in ClientError.response["Error"]["Code"].
_AWS_CODES: dict[str, ErrorCode] = {
    "UnrecognizedClientException": "invalid_key",
    "InvalidSignatureException": "invalid_key",
    "InvalidClientTokenId": "invalid_key",
    "SignatureDoesNotMatch": "invalid_key",
    "ExpiredTokenException": "invalid_key",
    "ThrottlingException": "rate_limited",
    "TooManyRequestsException": "rate_limited",
    "ServiceQuotaExceededException": "quota_exceeded",
    "ResourceNotFoundException": "model_not_found",
    "ModelNotReadyException": "provider_unreachable",
    "ModelTimeoutException": "provider_unreachable",
    "ServiceUnavailableException": "provider_unreachable",
    "InternalServerException": "provider_unreachable",
}


def from_aws(code: str, message: str | None) -> ProviderError:
    text = (message or "").lower()
    detail = _clip(message)
    if code in _AWS_CODES:
        return ProviderError(_AWS_CODES[code], detail)
    if code == "AccessDeniedException":
        # AWS answers this both for a bad credential and for a model the account
        # has not been granted; the message tells them apart.
        return ProviderError("model_not_found" if "model" in text else "invalid_key", detail)
    if code == "ValidationException" and "model" in text:
        return ProviderError("model_not_found", detail)
    return ProviderError("provider_rejected", detail)
