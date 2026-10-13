from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_initial_migration_creates_schema_and_seed_roles(tmp_path, monkeypatch):
    database_file = tmp_path / "migration.db"
    database_url = f"sqlite:///{database_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    from app.config import get_settings

    get_settings.cache_clear()
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        engine = create_engine(database_url)
        try:
            inspector = inspect(engine)
            assert {"roles", "sessions", "turns", "session_events", "sources", "memories"}.issubset(
                set(inspector.get_table_names())
            )
            with engine.connect() as connection:
                role_ids = {row[0] for row in connection.exec_driver_sql("SELECT id FROM roles")}
            assert role_ids == {"role_a", "role_b"}
        finally:
            engine.dispose()
    finally:
        get_settings.cache_clear()
