"""Makes a follow-up question stand on its own, and tells what kind of question it is."""

import json
import re

from scirag.providers.base import Message, ModelProvider
from scirag.rag.prompts import ANALYZE_SYSTEM, REWRITE_SYSTEM
from scirag.rag.types import Mode

HISTORY_MESSAGES = 12
MESSAGE_CHARS = 1500
MAX_QUESTION_CHARS = 1000


def clipped(history: list[Message]) -> list[Message]:
    """The last few turns, each cut to a size that keeps the prompt small."""
    return [
        {"role": message["role"], "content": message["content"][:MESSAGE_CHARS]}
        for message in history[-HISTORY_MESSAGES:]
    ]


def _transcript(history: list[Message]) -> str:
    return "\n".join(f"{message['role']}: {message['content']}" for message in clipped(history))


def _usable(rewritten: object, question: str) -> str:
    """The rewritten question, or the one the user wrote when the rewrite is no question."""
    if not isinstance(rewritten, str):
        return question
    rewritten = rewritten.replace("\x00", "").strip()
    # An empty or runaway reply is not a question; search with what the user wrote.
    return rewritten if 0 < len(rewritten) <= MAX_QUESTION_CHARS else question


def parse_analysis(reply: str, question: str) -> tuple[Mode, str]:
    """The kind of question and its rewritten form, from the model's reply.

    A reply that cannot be read, or names no known kind, is a factual question
    as the user wrote it: the cheapest path, and the right one most of the time.
    """
    try:
        parsed = json.loads(reply)
    except ValueError:
        # Some models wrap the JSON in prose or a code fence.
        found = re.search(r"\{.*\}", reply, re.DOTALL)
        try:
            parsed = json.loads(found.group()) if found else None
        except ValueError:
            parsed = None
    if not isinstance(parsed, dict):
        return "factual", question
    kind = parsed.get("type")
    mode: Mode = kind if kind in ("comparison", "synthesis") else "factual"
    return mode, _usable(parsed.get("question"), question)


async def analyze(
    provider: ModelProvider, history: list[Message], question: str
) -> tuple[Mode, str]:
    """What kind of question this is, and the question standing on its own."""
    conversation = f"Conversation:\n{_transcript(history)}\n\n" if history else ""
    reply = await provider.complete(
        [{"role": "user", "content": f"{conversation}Last question: {question}"}],
        role="fast",
        # The reply is one short object; the room is for a model that reasons first.
        max_tokens=1024,
        system=ANALYZE_SYSTEM,
        json_output=True,
    )
    return parse_analysis(reply, question)


async def rewrite(provider: ModelProvider, history: list[Message], question: str) -> str:
    """The question with what it refers to in earlier turns written out.

    history is not empty: a first question already stands alone and is not sent here.
    """
    transcript = _transcript(history)
    reply = await provider.complete(
        [
            {
                "role": "user",
                "content": f"Conversation:\n{transcript}\n\nLast question: {question}",
            }
        ],
        role="fast",
        max_tokens=256,
        system=REWRITE_SYSTEM,
    )
    return _usable(reply, question)
