"""Text types shared by the request schemas."""

from typing import Annotated

from pydantic import AfterValidator


def _reject_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("must not contain the NUL character")
    return value


# PostgreSQL cannot store NUL in text, so it is refused here instead of failing in the database.
NoNul = AfterValidator(_reject_nul)
Text = Annotated[str, NoNul]
