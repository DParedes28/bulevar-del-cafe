from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from core.config import get_settings

_engine = None


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgresql") and "sslmode=" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}sslmode=require"
    return url


def get_engine():
    global _engine
    if _engine is None:
        url = normalize_database_url(get_settings().database_url)
        connect_args = {"prepare_threshold": None} if url.startswith("postgresql") else {}
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            connect_args=connect_args,
        )
    return _engine


def init_db() -> None:
    import core.models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


@contextmanager
def open_session() -> Iterator[Session]:
    session = Session(get_engine())
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    with open_session() as session:
        yield session
