import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

# check_same_thread=False: SQLite's default forbids using a connection from
# a thread other than the one that created it. We create a fresh Session
# (and thus a fresh connection checkout) per operation from both FastAPI's
# request threads and each camera's background thread, never sharing one
# across threads concurrently, so this is safe.
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# Columns added after a table first shipped. create_all() only creates missing
# tables, so these are added to existing databases with ALTER TABLE.
_ADDED_COLUMNS = {
    "alerts": {
        "details": "TEXT",
        "dedupe_key": "VARCHAR",
        "occurrences": "INTEGER DEFAULT 1",
        "resolved_at": "DATETIME",
        "resolved_by": "VARCHAR",
    },
    "zones": {
        "loiter_seconds": "INTEGER DEFAULT 30",
        "repeat_entries": "INTEGER DEFAULT 3",
        "repeat_window_seconds": "INTEGER DEFAULT 300",
    },
}


def _add_missing_columns() -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in _ADDED_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def init_db() -> None:
    db_path = settings.database_url.removeprefix("sqlite:///")
    if db_path:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    from app.db import models  # noqa: F401  registers models on Base before create_all

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    if db_path and Path(db_path).is_file():
        os.chmod(db_path, 0o600)  # holds face embeddings: owner-only
