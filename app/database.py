from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import BASE_DIR, get_settings

settings = get_settings()


def _resolve_database_url(url: str) -> str:
    """A relative sqlite:///./data/x.db path must not depend on the process's
    current working directory (which varies: uvicorn --reload, a Windows
    service, a shortcut, --app-dir, ...). Anchor it to the project root
    instead, same as the absolute-path default in config.py."""
    if not url.startswith("sqlite:///"):
        return url
    raw_path = url[len("sqlite:///"):]
    if raw_path in ("", ":memory:") or Path(raw_path).is_absolute():
        return url
    return f"sqlite:///{(BASE_DIR / raw_path).resolve().as_posix()}"


database_url = _resolve_database_url(settings.database_url)

connect_args = {}
if database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    db_path = database_url.split("///")[-1]
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
