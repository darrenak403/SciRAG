"""How the API hands work to the worker: by name, through the queue in PostgreSQL.

Nothing here imports the workflows, so the API needs neither the parser nor a
running workflow engine.
"""

import uuid
from functools import lru_cache

from dbos import DBOSClient, run_dbos_database_migrations
from dbos import error as dbos_errors
from sqlalchemy.engine import make_url

from scientrag.config import get_settings

INGEST_QUEUE = "ingest"
INGEST_WORKFLOW = "ingest_paper"
DELETE_WORKFLOW = "delete_paper"
# Recovery only resumes workflows of the same version. The default is a hash of
# the code, which would strand every paper in progress on each deploy. Change it
# when the list of steps changes: a workflow recorded with the old steps cannot be
# resumed with the new ones.
APPLICATION_VERSION = "1"


def system_database_url() -> str:
    """The application database, in the plain form the workflow engine expects."""
    url = make_url(get_settings().database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


@lru_cache
def _client() -> DBOSClient:
    return DBOSClient(system_database_url=system_database_url())


async def _enqueue(workflow: str, deduplication_id: str, *arguments: str) -> bool:
    try:
        await _client().enqueue_async(
            {
                "workflow_name": workflow,
                "queue_name": INGEST_QUEUE,
                "deduplication_id": deduplication_id,
                "app_version": APPLICATION_VERSION,
            },
            *arguments,
        )
    except dbos_errors.DBOSQueueDeduplicatedError:
        return False
    return True


async def enqueue_ingest(paper_id: uuid.UUID, first_step: str = "parse") -> bool:
    """Queues the paper for processing. False if it is already queued or being processed."""
    return await _enqueue(INGEST_WORKFLOW, str(paper_id), str(paper_id), first_step)


async def enqueue_delete(paper_id: uuid.UUID) -> bool:
    return await _enqueue(DELETE_WORKFLOW, f"delete:{paper_id}", str(paper_id))


def create_tables() -> None:
    """Creates or upgrades the workflow engine's tables (schema "dbos").

    Run with the database migrations, so the API can queue a paper before any
    worker has ever started.
    """
    run_dbos_database_migrations(system_database_url())


if __name__ == "__main__":
    create_tables()
