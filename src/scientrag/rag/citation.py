"""Checks the source markers a model wrote against the passages it was given."""

import re

# [S1], and the grouped form models also write: [S1, S2].
_MARKERS = re.compile(r"([ \t]*)(\[\s*S\d+(?:\s*[,;]\s*S\d+)*\s*\])")
_ID = re.compile(r"S\d+")
# Fenced blocks and inline code: what is inside is quoted text, not a citation.
_CODE = re.compile(r"```.*?(?:```|\Z)|`[^`\n]*`", re.DOTALL)
# The ways models are seen to disguise a marker: zero-width space, word joiner and
# byte order mark inside the brackets, and the brackets written as \u3010 \u3011.
_AS_WRITTEN = str.maketrans(
    {"\u200b": None, "\u2060": None, "\ufeff": None, "\u3010": "[", "\u3011": "]"}
)


def plain(text: str) -> str:
    """The model's text with markers in the one form the check and the reader's
    screen know: "[S1]". Applied piece by piece as the answer streams, so it only
    maps single characters."""
    return text.translate(_AS_WRITTEN)


def validate(text: str, valid: set[str]) -> tuple[str, list[str]]:
    """Removes markers that name no passage. Returns the clean text and the markers used.

    valid holds the ids the model was given ("S1", ...). The markers used come
    back in the order they first appear. Text inside code is left as it is.
    """
    used: list[str] = []

    def keep_valid(match: re.Match[str]) -> str:
        kept = [marker for marker in _ID.findall(match.group(2)) if marker in valid]
        used.extend(marker for marker in kept if marker not in used)
        # A marker removed whole takes the space before it along: "claim [S9]." -> "claim."
        return match.group(1) + "".join(f"[{m}]" for m in dict.fromkeys(kept)) if kept else ""

    def clean(prose: str) -> str:
        return _MARKERS.sub(keep_valid, prose)

    pieces: list[str] = []
    position = 0
    for code in _CODE.finditer(text):
        pieces += [clean(text[position : code.start()]), code.group()]
        position = code.end()
    pieces.append(clean(text[position:]))
    return "".join(pieces).strip(), used


def without_markers(text: str) -> str:
    """The text with every marker removed, for an answer whose passages are no longer at hand."""
    return _MARKERS.sub("", text)


def markers(text: str) -> list[str]:
    """Every marker written in the text, in order and with repeats. Code is left out."""
    prose = _CODE.sub("", text)
    return [marker for match in _MARKERS.finditer(prose) for marker in _ID.findall(match.group(2))]
