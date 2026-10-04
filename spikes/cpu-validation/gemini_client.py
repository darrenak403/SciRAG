"""Thin REST client for the Gemini API: embeddings, and an LLM used as a listwise reranker.

Only what the spike needs. One key (GEMINI_API_KEY) covers both.
"""

import json
import os
import time

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta/models"
EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL") or "gemini-embedding-2"
RERANK_MODEL = os.environ.get("GEMINI_RERANK_MODEL") or "gemini-3.5-flash-lite"
DIMENSIONS = int(os.environ.get("GEMINI_EMBED_DIMENSIONS") or 768)
BATCH_SIZE = 50

# One shared client so timings measure the API, not a new TLS handshake per call.
_client = httpx.Client(timeout=120)
# Retries (HTTP 429 / 5xx) inflate timings; run.py records the count next to them.
retry_count = 0


def api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def _post(path: str, payload: dict) -> dict:
    global retry_count
    for attempt in range(6):
        response = _client.post(f"{BASE}/{path}", json=payload, headers={"x-goog-api-key": api_key()})
        if response.status_code == 429 or response.status_code >= 500:
            retry_count += 1
            wait = float(response.headers.get("retry-after", 2 ** (attempt + 1)))
            print(f"  gemini: HTTP {response.status_code}, retrying in {wait:.0f}s")
            time.sleep(wait)
            continue
        if response.is_error:
            raise RuntimeError(f"gemini {path}: HTTP {response.status_code} {response.text[:300]}")
        return response.json()
    raise RuntimeError(f"gemini {path}: still rate limited after 6 attempts")


def embed(texts: list[str], kind: str) -> list[list[float]]:
    """kind is "query" or "document". gemini-embedding-2 takes the task as a text prefix."""
    prefix = "task: search result | query: " if kind == "query" else "title: none | text: "
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        body = _post(
            f"{EMBED_MODEL}:batchEmbedContents",
            {
                "requests": [
                    {
                        "model": f"models/{EMBED_MODEL}",
                        "content": {"parts": [{"text": prefix + text}]},
                        "output_dimensionality": DIMENSIONS,
                    }
                    for text in texts[start : start + BATCH_SIZE]
                ]
            },
        )
        vectors += [row["values"] for row in body["embeddings"]]
    return vectors


def rerank(query: str, documents: list[str], top_n: int) -> list[int]:
    """Asks the LLM for the indices of the most relevant passages, best first."""
    passages = "\n\n".join(f"[{index}] {text}" for index, text in enumerate(documents))
    prompt = (
        f"Question: {query}\n\nPassages:\n{passages}\n\n"
        f"Return the indices of the {top_n} passages most useful for answering the question, "
        "most useful first. Only use indices that appear above."
    )
    body = _post(
        f"{RERANK_MODEL}:generateContent",
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": {"type": "ARRAY", "items": {"type": "INTEGER"}},
            },
        },
    )
    order = json.loads(body["candidates"][0]["content"]["parts"][0]["text"])
    # The model can repeat or invent indices; keep the valid ones in the order given.
    seen: list[int] = []
    for index in order:
        if 0 <= index < len(documents) and index not in seen:
            seen.append(index)
    return seen[:top_n]
