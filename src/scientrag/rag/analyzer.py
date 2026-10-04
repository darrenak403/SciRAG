"""Makes a follow-up question stand on its own, so it can be searched for."""

from scientrag.providers.base import Message, ModelProvider
from scientrag.rag.prompts import REWRITE_SYSTEM

HISTORY_MESSAGES = 12
MESSAGE_CHARS = 1500
MAX_QUESTION_CHARS = 1000


def clipped(history: list[Message]) -> list[Message]:
    """The last few turns, each cut to a size that keeps the prompt small."""
    return [
        {"role": message["role"], "content": message["content"][:MESSAGE_CHARS]}
        for message in history[-HISTORY_MESSAGES:]
    ]


async def rewrite(provider: ModelProvider, history: list[Message], question: str) -> str:
    """The question with what it refers to in earlier turns written out.

    history is not empty: a first question already stands alone and is not sent here.
    """
    transcript = "\n".join(
        f"{message['role']}: {message['content']}" for message in clipped(history)
    )
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
    rewritten = reply.replace("\x00", "").strip()
    # An empty or runaway reply is not a question; search with what the user wrote.
    return rewritten if 0 < len(rewritten) <= MAX_QUESTION_CHARS else question
