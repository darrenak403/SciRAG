"""Models used when the account has not chosen one, per kind of connection."""

from scirag.providers.base import Role

DEFAULT_MODELS: dict[str, dict[Role, str]] = {
    "gemini": {
        "answer": "gemini-3.5-flash",
        "fast": "gemini-3.5-flash-lite",
        "embedding": "gemini-embedding-2",
    },
    "bedrock": {
        "answer": "amazon.nova-pro-v1:0",
        "fast": "amazon.nova-lite-v1:0",
        "embedding": "amazon.titan-embed-text-v2:0",
    },
    # Nothing can be assumed about a self-hosted router: the account picks every model.
    "openai_compatible": {},
}

# Vector size asked of the embedding models whose size can be chosen.
GEMINI_EMBEDDING_DIMENSION = 768
TITAN_EMBEDDING_DIMENSION = 1024


def models_for(kind: str, chosen: dict[str, str]) -> dict[Role, str]:
    """The account's choices on top of the defaults for this kind of connection."""
    return {**DEFAULT_MODELS[kind], **chosen}
