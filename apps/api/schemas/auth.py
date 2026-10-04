import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# Deliberately loose: one "@" with something on both sides. Real validation of an
# address is sending mail to it, which this system does not do.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=320,
        pattern=r"^[^@\s\x00]+@[^@\s\x00]+\.[^@\s\x00]+$",
    ),
]


class Credentials(BaseModel):
    email: Email
    password: str = Field(min_length=8, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    active_connection_id: uuid.UUID | None
