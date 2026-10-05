"""Alembic environment. Runs migrations over a plain synchronous connection."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

import scirag.db.models  # noqa: F401  (registers the tables on Base.metadata)
from scirag.config import get_settings
from scirag.db.base import Base

if context.config.config_file_name:
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations() -> None:
    # The psycopg driver serves both sync and async engines from the same URL.
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
