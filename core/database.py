from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
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

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _migrate_observations(engine)
    _migrate_location(engine)


def _migrate_observations(engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(text("LOCK TABLE observations IN ACCESS EXCLUSIVE MODE"))
        columns = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'observations'"
                )
            )
        }
        if "owner_document" in columns or "owner_email" not in columns:
            return
        connection.execute(text("ALTER TABLE observations ADD COLUMN owner_document VARCHAR(20)"))
        connection.execute(text("ALTER TABLE observations ADD COLUMN page_number INTEGER"))
        connection.execute(text("ALTER TABLE observations ADD COLUMN article VARCHAR(80) NOT NULL DEFAULT ''"))
        connection.execute(
            text(
                """
                UPDATE observations
                SET owner_document = LEFT(btrim(owner_email), 20),
                    page_number = COALESCE(
                        NULLIF(substring(article_or_page FROM '([0-9]+)'), '')::integer,
                        1
                    ),
                    article = LEFT(
                        btrim(COALESCE(substring(article_or_page FROM '·[[:space:]]*(.*)$'), '')),
                        80
                    )
                """
            )
        )
        connection.execute(text("ALTER TABLE observations DROP CONSTRAINT IF EXISTS observations_article_chk"))
        connection.execute(text("ALTER TABLE observations DROP COLUMN owner_email"))
        connection.execute(text("ALTER TABLE observations DROP COLUMN article_or_page"))
        connection.execute(text("ALTER TABLE observations ALTER COLUMN owner_document SET NOT NULL"))
        connection.execute(text("ALTER TABLE observations ALTER COLUMN page_number SET NOT NULL"))
        connection.execute(
            text(
                "ALTER TABLE observations ADD CONSTRAINT observations_document_chk "
                "CHECK (char_length(btrim(owner_document)) BETWEEN 1 AND 20)"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE observations ADD CONSTRAINT observations_page_chk "
                "CHECK (page_number BETWEEN 1 AND 9999)"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE observations ADD CONSTRAINT observations_article_chk "
                "CHECK (char_length(article) <= 80)"
            )
        )


def _migrate_location(engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(740231)"))
        columns = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'observations'"
                )
            )
        }
        if "etapa" not in columns:
            connection.execute(text("ALTER TABLE observations ADD COLUMN IF NOT EXISTS etapa VARCHAR(1)"))
        if "manzana" not in columns:
            connection.execute(text("ALTER TABLE observations ADD COLUMN IF NOT EXISTS manzana VARCHAR(20)"))
        present = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conname IN ('observations_etapa_chk', 'observations_manzana_chk')"
                )
            )
        }
        if "observations_etapa_chk" not in present:
            connection.execute(
                text(
                    "ALTER TABLE observations ADD CONSTRAINT observations_etapa_chk "
                    "CHECK (etapa IS NULL OR etapa IN ('1', '2'))"
                )
            )
        if "observations_manzana_chk" not in present:
            connection.execute(
                text(
                    "ALTER TABLE observations ADD CONSTRAINT observations_manzana_chk "
                    "CHECK (manzana IS NULL OR char_length(btrim(manzana)) BETWEEN 1 AND 20)"
                )
            )


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
