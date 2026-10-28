from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def resolve_sqlite_url(url: str, root: Path = BACKEND_ROOT) -> str:
    """Anchor relative SQLite paths to the backend directory.

    Without this the database file depends on the current working directory,
    which is how the application and Alembic drifted onto different files.
    """
    if not url.startswith("sqlite"):
        return url
    scheme, separator, path = url.partition(":///")
    if not separator or not path or path == ":memory:" or path.startswith("/"):
        return url
    return f"{scheme}:///{(root / path).resolve()}"


class Settings(BaseSettings):
    # The .env files are resolved absolutely so the working directory of the
    # process (repository root, backend/, ...) cannot change the configuration.
    model_config = SettingsConfigDict(
        env_prefix="MARGARITINI_",
        env_file=(BACKEND_ROOT.parent / ".env", BACKEND_ROOT / ".env"),
        extra="ignore",
    )

    database_url: str = "sqlite:///./margaritini.db"
    cors_origins: list[str] = [
        "http://localhost:6002",
        "http://127.0.0.1:6002",
    ]
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]"]
    max_import_nodes: int = 2000
    max_import_tasks: int = 20000
    max_request_bytes: int = 5_000_000
    api_token: str | None = None

    @property
    def resolved_database_url(self) -> str:
        return resolve_sqlite_url(self.database_url)


settings = Settings()
