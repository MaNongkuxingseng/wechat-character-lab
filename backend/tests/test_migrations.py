from pathlib import Path

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
        backend_dir = Path(__file__).resolve().parents[1]
        config = Config(str(backend_dir / "alembic.ini"))
        config.set_main_option("script_location", str(backend_dir / "alembic"))
        command.upgrade(config, "head")
        engine = create_engine(database_url)
        try:
            inspector = inspect(engine)
            assert {
                "roles",
                "sessions",
                "turns",
                "session_events",
                "sources",
                "memories",
                "profile_versions",
                "profile_traits",
                "profile_evidence",
                "profile_candidate_snapshots",
                "profile_candidate_items",
                "profile_candidate_evidence",
                "profile_candidate_review_events",
                "voice_analyses",
                "provider_configuration",
            }.issubset(set(inspector.get_table_names()))
            with engine.connect() as connection:
                role_ids = {row[0] for row in connection.exec_driver_sql("SELECT id FROM roles")}
            assert role_ids == {"role_a", "role_b"}
        finally:
            engine.dispose()
    finally:
        get_settings.cache_clear()


def test_candidate_migration_downgrade_removes_only_candidate_tables(tmp_path, monkeypatch):
    database_file = tmp_path / "candidate-migration.db"
    database_url = f"sqlite:///{database_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    from app.config import get_settings

    get_settings.cache_clear()
    try:
        backend_dir = Path(__file__).resolve().parents[1]
        config = Config(str(backend_dir / "alembic.ini"))
        config.set_main_option("script_location", str(backend_dir / "alembic"))
        command.upgrade(config, "head")
        command.downgrade(config, "0003_voice_analysis")
        engine = create_engine(database_url)
        try:
            tables = set(inspect(engine).get_table_names())
            assert not {
                "profile_candidate_snapshots",
                "profile_candidate_items",
                "profile_candidate_evidence",
                "profile_candidate_review_events",
            } & tables
            assert {
                "roles",
                "profile_versions",
                "profile_traits",
                "profile_evidence",
                "voice_analyses",
            }.issubset(tables)
            assert "provider_configuration" not in tables
        finally:
            engine.dispose()
    finally:
        get_settings.cache_clear()


def test_candidate_migration_keeps_source_id_external_and_mapped_id_as_fk(
    tmp_path, monkeypatch
):
    database_file = tmp_path / "candidate-contract.db"
    database_url = f"sqlite:///{database_file.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    from app.config import get_settings

    get_settings.cache_clear()
    try:
        backend_dir = Path(__file__).resolve().parents[1]
        config = Config(str(backend_dir / "alembic.ini"))
        config.set_main_option("script_location", str(backend_dir / "alembic"))
        command.upgrade(config, "head")
        engine = create_engine(database_url)
        try:
            inspector = inspect(engine)
            evidence_foreign_keys = inspector.get_foreign_keys("profile_candidate_evidence")
            constrained_columns = {
                column
                for foreign_key in evidence_foreign_keys
                for column in foreign_key["constrained_columns"]
            }
            assert "source_message_id" not in constrained_columns
            assert "imported_message_id" in constrained_columns
            imported_reference = next(
                item
                for item in evidence_foreign_keys
                if item["constrained_columns"] == ["imported_message_id"]
            )
            assert imported_reference["referred_table"] == "imported_messages"
            unique_constraints = inspector.get_unique_constraints("profile_candidate_evidence")
            assert any(
                item["name"] == "uq_candidate_evidence_source_message"
                and item["column_names"] == ["candidate_id", "source_message_id"]
                for item in unique_constraints
            )
        finally:
            engine.dispose()
    finally:
        get_settings.cache_clear()
