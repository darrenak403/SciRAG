"""The ingestion worker: takes papers off the queue and runs their workflows."""

import threading

from dbos import DBOS

from scirag.auth.secrets import get_fernet
from scirag.config import get_settings
from scirag.ingestion import workflow  # noqa: F401  (registers the workflows and the queue)
from scirag.ingestion.queue import APPLICATION_VERSION, INGEST_QUEUE, system_database_url


def launch() -> None:
    DBOS(
        config={
            # The name the workflow tables were created under: the engine refuses another.
            "name": "scientrag",
            "system_database_url": system_database_url(),
            "application_version": APPLICATION_VERSION,
        }
    )
    DBOS.launch()
    # Ingest and delete share the queue, so with one paper at a time a delete never
    # runs alongside a step that is writing the same paper.
    DBOS.register_queue(
        INGEST_QUEUE,
        worker_concurrency=get_settings().ingest_concurrency,
        on_conflict="always_update",
    )


def main() -> None:
    # Fail at startup, not on the first paper, when SECRETS_KEY is malformed.
    get_fernet()
    launch()
    threading.Event().wait()


if __name__ == "__main__":
    main()
