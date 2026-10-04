"""Request and response shapes for model-provider connections.

Credentials only ever travel inward. No response model has a field for them.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from apps.api.schemas.text import Text

Label = Annotated[Text, Field(min_length=1, max_length=100)]
Key = Annotated[str, Field(min_length=8, max_length=4096)]


class Models(BaseModel):
    """Model chosen for each role. A role left out uses the provider's default."""

    answer: Text | None = Field(default=None, max_length=200)
    fast: Text | None = Field(default=None, max_length=200)
    embedding: Text | None = Field(default=None, max_length=200)


class GeminiCreate(BaseModel):
    kind: Literal["gemini"]
    label: Label
    api_key: Key
    models: Models = Models()


class BedrockCreate(BaseModel):
    kind: Literal["bedrock"]
    label: Label
    region: str = Field(pattern=r"^[a-z]{2}(-[a-z]+)+-\d$")
    access_key_id: Key
    secret_access_key: Key
    models: Models = Models()


class OpenAICompatibleCreate(BaseModel):
    kind: Literal["openai_compatible"]
    label: Label
    # http(s) only; HttpUrl rejects every other scheme.
    base_url: HttpUrl
    api_key: Key
    models: Models = Models()

    @field_validator("base_url")
    @classmethod
    def _no_credentials_in_url(cls, url: HttpUrl) -> HttpUrl:
        # The URL is stored unencrypted and shown back; the key belongs in api_key.
        if url.username or url.password:
            raise ValueError("must not contain a username or password")
        return url


ConnectionCreate = Annotated[
    GeminiCreate | BedrockCreate | OpenAICompatibleCreate, Field(discriminator="kind")
]


class ConnectionUpdate(BaseModel):
    """Fields left out are not changed.

    To replace the credentials, send the credential fields of the connection's
    kind: api_key, or access_key_id together with secret_access_key for Bedrock.
    """

    label: Label | None = None
    models: Models | None = None
    api_key: Key | None = None
    access_key_id: Key | None = None
    secret_access_key: Key | None = None


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    label: str
    config: dict[str, Any]
    secret_last4: str
    # Result of the last capability test: each check, and whether the connection can be used.
    capabilities: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ActiveConnectionChoice(BaseModel):
    connection_id: uuid.UUID | None


class ModelList(BaseModel):
    models: list[str]


class UsageRow(BaseModel):
    connection_id: uuid.UUID | None
    model: str
    role: str
    input_tokens: int
    output_tokens: int
