from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import BACKEND_ROOT, settings
from app.db.database import Base
from sqlalchemy import create_engine, inspect


def alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


def test_alembic_ini_does_not_pin_a_database_url() -> None:
    assert not (alembic_config().get_main_option("sqlalchemy.url") or "").strip()


def test_migrations_build_the_model_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{tmp_path / 'migration_check.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    command.upgrade(alembic_config(), "head")

    inspector = inspect(create_engine(url))
    assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {
        "alembic_version"
    }
    for name, table in Base.metadata.tables.items():
        migrated = {column["name"] for column in inspector.get_columns(name)}
        assert migrated == {column.name for column in table.columns}
