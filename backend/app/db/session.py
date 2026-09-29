from pathlib import Path

from sqlalchemy import create_engine
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


def init_db() -> None:
    db_path = settings.database_url.removeprefix("sqlite:///")
    if db_path:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    from app.db import models  # noqa: F401  registers models on Base before create_all

    Base.metadata.create_all(bind=engine)
