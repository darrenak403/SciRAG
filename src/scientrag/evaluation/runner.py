"""Runs a question set through the system and scores what comes back.

Two modes. retrieval stops each question once the passages are chosen: no
answer is written, so many configurations can be compared cheaply. answer lets
the question run to the end and scores the answer and its citations as well.

Both go through rag.engine.answer, the path a user's question takes.
"""

import asyncio
import os
import random
import tomllib
from contextlib import aclosing
from dataclasses import asdict, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ConfigDict, TypeAdapter
from pydantic.dataclasses import dataclass

from scientrag.config import get_settings
from scientrag.db.models import ProviderConnection
from scientrag.evaluation import corpus, judges, metrics
from scientrag.evaluation.datasets import golden, qasper
from scientrag.evaluation.datasets.base import EvalDataset, EvalQuestion
from scientrag.evaluation.evidence_mapping import covering_chunks
from scientrag.providers.base import ModelProvider
from scientrag.providers.errors import ProviderError
from scientrag.providers.resolve import connection_provider
from scientrag.rag import citation, engine
from scientrag.rag.types import Delta, Done, Sources

# The settings an experiment may change. Anything else stays as the application runs it.
TUNABLE = frozenset(
    {
        "search_candidates",
        "search_fusion",
        "rerank_candidates",
        "rerank_enabled",
        "context_chunks",
        "context_max_tokens",
        "answer_max_tokens",
    }
)
RECALL_AT = (1, 3, 5, 8)


# Checked when read: a mistyped mode or dataset stops the run instead of running as another.
@dataclass(frozen=True, config=ConfigDict(strict=True, extra="forbid"))
class RunConfig:
    name: str
    dataset: Literal["qasper", "golden"]
    mode: Literal["retrieval", "answer"] = "retrieval"
    # QASPER only: how many papers of the development split, and the seed that picks them.
    papers: int = 100
    seed: int = 7
    # Ask only this many questions, picked by the seed. None: all of them.
    questions: int | None = None
    # question: each question searches its own papers. corpus: every paper of the dataset.
    scope: Literal["question", "corpus"] = "question"
    chunk_max_tokens: int = 400
    concurrency: int = 4
    # answer mode: also score the answers with a model as judge.
    judge: bool = False
    settings: dict[str, Any] = field(default_factory=dict)
    provider: dict[str, Any] = field(
        default_factory=lambda: {"kind": "gemini", "key_env": "GEMINI_API_KEY"}
    )

    @classmethod
    def from_file(cls, path: Path) -> RunConfig:
        config = cls(**tomllib.loads(path.read_text()))
        unknown = set(config.settings) - TUNABLE
        if unknown:
            raise SystemExit(f"{path}: not a setting an experiment can change: {sorted(unknown)}")
        return config


# What the application runs with, kept from before the first experiment changed anything.
_APPLICATION: dict[str, Any] = {}


def _apply(config: RunConfig) -> dict[str, Any]:
    """Makes the application's settings those of the experiment. Returns the ones in force."""
    settings = get_settings()
    if not _APPLICATION:
        _APPLICATION.update({name: getattr(settings, name) for name in TUNABLE})
    settings.chunk_max_tokens = config.chunk_max_tokens
    # Thousands of questions would bury the traces of real ones.
    settings.otlp_endpoint = None
    # Experiments run one after another in a process: each starts from the application's values.
    for name, value in (_APPLICATION | config.settings).items():
        # A mistyped value would otherwise run as something else under the experiment's name.
        kind = type(settings).model_fields[name].annotation
        setattr(settings, name, TypeAdapter(kind).validate_python(value, strict=True))
    return {name: getattr(settings, name) for name in sorted(TUNABLE | {"chunk_max_tokens"})}


def _load(config: RunConfig, cache: Path) -> EvalDataset:
    if config.dataset == "qasper":
        return qasper.load(cache / "qasper", papers=config.papers, seed=config.seed)
    return golden.load(cache / "golden")


def _retrieval_scores(
    ranked: list[str], candidates: list[str], evidence: list[set[str]], context_chunks: int
) -> dict[str, float]:
    relevant = set().union(*evidence)
    scores = {
        f"recall@{k}": metrics.recall_at_k(ranked, evidence, k)
        for k in RECALL_AT
        if k <= context_chunks
    }
    scores["mrr"] = metrics.mrr(ranked, relevant)
    scores["ndcg"] = metrics.ndcg_at_k(ranked, relevant, context_chunks)
    # What the search found before reranking: the ceiling of what reranking can bring up.
    scores["candidate_recall"] = metrics.recall_at_k(candidates, evidence, len(candidates))
    return scores


async def _judge(
    provider: ModelProvider,
    question: EvalQuestion,
    answer: str,
    passages: dict[str, str],
    row: dict[str, Any],
) -> None:
    """Adds the judged scores to the row. Passages are keyed by marker, in ranked order."""
    ranked = list(passages.values())
    row["faithfulness"] = await judges.faithfulness(provider, answer, ranked)
    row["answer_relevance"] = await judges.answer_relevance(provider, question.text, answer)
    if question.reference:
        row["context_precision"] = await judges.context_precision(
            provider, question.text, question.reference, ranked
        )
        row["context_recall"] = await judges.context_recall(provider, question.reference, ranked)
    verdicts = await judges.citation_support(provider, answer, passages)
    if verdicts:
        row["citation_support"] = metrics.mean([float(item["supported"]) for item in verdicts])
        row["cited_sentences"] = verdicts


async def _ask(
    config: RunConfig,
    connection: ProviderConnection,
    judge: ModelProvider | None,
    question: EvalQuestion,
    paper_ids: list,
    chunks: dict[str, str],
    evidence: list[set[str]],
) -> dict[str, Any]:
    """One question, start to finish. chunks maps the id of every chunk in scope to its text."""
    row: dict[str, Any] = {
        "id": question.id,
        "question": question.text,
        "answerable": question.answerable,
    }
    sources: Sources | None = None
    done: Done | None = None
    written: list[str] = []
    try:
        answer = engine.answer(connection, question.text, paper_ids=paper_ids, history=[])
        async with aclosing(answer):
            async for event in answer:
                if isinstance(event, Sources):
                    sources = event
                    if config.mode == "retrieval":
                        # Closing here ends the question before any answer is paid for.
                        break
                elif isinstance(event, Delta):
                    written.append(event.text)
                else:
                    done = event
    except ProviderError as error:
        row["error"] = error.code
        return row
    except Exception as error:
        # One question that breaks is counted as an error; the rest of the run is kept.
        row["error"] = type(error).__name__
        return row

    retrieval = sources.retrieval
    if get_settings().rerank_enabled and retrieval.get("rerank") != "model":
        # The answer path falls back to the search order when the fast model fails.
        # Scored here, that question would pass for a reranked one.
        row["error"] = "rerank_failed"
        return row
    ranked = [str(source.chunk_id) for source in sources.sources]
    row["ranked"] = ranked
    if evidence:
        candidates = [item["chunk_id"] for item in retrieval.get("candidates", [])]
        row |= _retrieval_scores(ranked, candidates, evidence, get_settings().context_chunks)
    row["rerank"] = retrieval.get("rerank")
    if done is None:
        row |= {name: retrieval[name] for name in metrics.TIMINGS[:2] if name in retrieval}
        return row

    row |= {name: done.retrieval[name] for name in metrics.TIMINGS if name in done.retrieval}
    row["tokens"] = done.retrieval.get("tokens", {})
    row["answer"] = done.text
    row["outcome"] = done.outcome
    # Right when it answers what can be answered and declines what cannot.
    row["answered_correctly"] = float((done.outcome == "answered") == question.answerable)
    markers = citation.markers("".join(written))
    offered = {source.marker for source in sources.sources}
    if markers:
        row["marker_validity"] = sum(marker in offered for marker in markers) / len(markers)
    if question.reference and done.outcome == "answered":
        row["answer_f1"] = metrics.token_f1(citation.without_markers(done.text), question.reference)
    if judge is not None and done.outcome == "answered":
        passages = {source.marker: chunks[str(source.chunk_id)] for source in sources.sources}
        await _judge(judge, question, done.text, passages, row)
    return row


async def run(config: RunConfig, cache: Path) -> dict[str, Any]:
    started = datetime.now(UTC)
    in_force = _apply(config)
    dataset = _load(config, cache)
    connection = await corpus.ensure_account(
        corpus.account_email(config.chunk_max_tokens), config.provider
    )
    paper_ids = await corpus.ensure_papers(
        connection.user_id, dataset.name, list(dataset.papers.values())
    )
    texts = await corpus.chunk_texts(list(paper_ids.values()))

    questions = dataset.questions
    if config.questions and config.questions < len(questions):
        questions = random.Random(config.seed).sample(questions, config.questions)

    limit = asyncio.Semaphore(config.concurrency)
    unmapped = 0

    async def one(question: EvalQuestion, judge: ModelProvider | None) -> dict[str, Any]:
        nonlocal unmapped
        own = [paper_ids[key] for key in question.paper_keys]
        scope = list(paper_ids.values()) if config.scope == "corpus" else own
        own_chunks = [chunk for paper_id in own for chunk in texts[paper_id]]
        found = [covering_chunks(passage, own_chunks) for passage in question.evidence]
        unmapped += sum(1 for chunks in found if not chunks)
        evidence = [chunks for chunks in found if chunks]
        in_scope = {chunk_id: text for paper_id in scope for chunk_id, text in texts[paper_id]}
        async with limit:
            return await _ask(config, connection, judge, question, scope, in_scope, evidence)

    if config.mode == "answer" and config.judge:
        async with connection_provider(connection) as judge:
            rows = await asyncio.gather(*(one(question, judge) for question in questions))
    else:
        rows = await asyncio.gather(*(one(question, None) for question in questions))

    return {
        "name": config.name,
        "started_at": started.isoformat(),
        "commit": os.environ.get("GIT_COMMIT", "unknown"),
        "config": asdict(config),
        "settings": in_force,
        "models": {
            "kind": connection.kind,
            **(connection.config.get("models") or {}),
        },
        "dataset": {
            "name": dataset.name,
            "papers": len(dataset.papers),
            "questions": len(rows),
            "questions_with_evidence": sum(1 for row in rows if "mrr" in row),
            "evidence_passages_not_found_in_chunks": unmapped,
            "errors": sum(1 for row in rows if "error" in row),
        },
        "metrics": metrics.summary(rows),
        "rows": rows,
    }
