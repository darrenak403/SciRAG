"""The durable workflows the worker runs.

DBOS records every finished step in PostgreSQL. A worker that dies mid-paper
picks the workflow up again at the step that was running.
"""

import uuid
from typing import Any

from dbos import DBOS
from dbos import error as dbos_errors

from scientrag.ingestion import steps
from scientrag.ingestion.errors import PaperGone, PermanentIngestionError
from scientrag.ingestion.queue import DELETE_WORKFLOW, INGEST_WORKFLOW
from scientrag.providers.errors import ProviderError

MAX_ATTEMPTS = 3


def should_retry(error: BaseException) -> bool:
    """Only failures that can pass on their own are tried again."""
    if isinstance(error, PermanentIngestionError | PaperGone):
        return False
    if isinstance(error, ProviderError):
        return error.retryable
    return True


def failure_of(error: BaseException) -> tuple[str, str]:
    """The error code and the message shown to the paper's owner."""
    if isinstance(error, dbos_errors.DBOSMaxStepRetriesExceeded):
        last = error.errors[-1] if error.errors else None
        if isinstance(last, ProviderError):
            return last.code, str(last)
        return "temporary_failure", "Processing kept failing. Try again in a while."
    if isinstance(error, PermanentIngestionError):
        return error.code, str(error)
    if isinstance(error, ProviderError):
        return error.code, str(error)
    return "temporary_failure", "Processing failed unexpectedly. Try again in a while."


def _durable(name: str):
    @DBOS.step(
        name=name,
        retries_allowed=True,
        max_attempts=MAX_ATTEMPTS,
        interval_seconds=5,
        backoff_rate=3,
        # Looked up on each failure, so the rule can be replaced in tests.
        should_retry=lambda error: should_retry(error),
    )
    async def run(paper_id: str) -> dict[str, Any]:
        attempt = (DBOS.step_status.current_attempt or 0) + 1
        return await steps.run_step(name, uuid.UUID(paper_id), attempt, steps.WORK[name])

    return run


RUN = {name: _durable(name) for name in steps.STEPS}


@DBOS.step(name="mark_failed", retries_allowed=True, max_attempts=MAX_ATTEMPTS)
async def _mark_failed(paper_id: str, code: str, message: str, keep_ready: bool) -> None:
    await steps.mark_failed(uuid.UUID(paper_id), code, message, keep_ready=keep_ready)


@DBOS.step(name="remove", retries_allowed=True, max_attempts=MAX_ATTEMPTS, interval_seconds=5)
async def _remove(paper_id: str) -> None:
    await steps.remove(uuid.UUID(paper_id))


# A paper that kills the worker every time it is parsed is given up on after a few
# restarts instead of taking the worker down forever.
@DBOS.workflow(name=INGEST_WORKFLOW, max_recovery_attempts=5)
async def ingest_paper(paper_id: str, first_step: str = "parse") -> None:
    """Takes a paper to READY, starting at first_step. Re-indexing starts at "embed"."""
    name = first_step
    try:
        for name in steps.STEPS[steps.STEPS.index(first_step) :]:
            await RUN[name](paper_id)
    except PaperGone:
        return
    except Exception as error:
        code, message = failure_of(error)
        DBOS.logger.warning(f"paper {paper_id} failed with {code}: {type(error).__name__}")
        # A re-index that fails while embedding has not touched the index: the paper
        # is as searchable as before, so it stays READY with the reason attached.
        keep_ready = first_step == "embed" and name == "embed"
        await _mark_failed(paper_id, code, message, keep_ready)


@DBOS.workflow(name=DELETE_WORKFLOW)
async def delete_paper(paper_id: str) -> None:
    await _remove(paper_id)
