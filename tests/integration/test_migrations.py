from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import scientrag.db.models  # noqa: F401  (registers the tables on Base.metadata)
from scientrag.config import get_settings
from scientrag.db.base import Base


def test_migrations_produce_the_schema_the_models_describe():
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert differences == []


def test_downgrade_removes_everything_and_upgrade_restores_it(alembic_config: Config):
    engine = create_engine(get_settings().database_url)

    command.downgrade(alembic_config, "base")
    with engine.connect() as connection:
        assert inspect(connection).get_table_names() == ["alembic_version"]

    command.upgrade(alembic_config, "head")
    with engine.connect() as connection:
        assert set(inspect(connection).get_table_names()) == {
            "alembic_version",
            *Base.metadata.tables,
        }
    engine.dispose()
