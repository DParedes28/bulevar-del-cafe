import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient
from sqlalchemy.pool import NullPool

import core.database as database
from web import main


def test_health_get_head_sin_base(monkeypatch):
    def fail():
        raise AssertionError("no debe abrir la base")

    monkeypatch.setattr(database, "get_engine", fail)
    monkeypatch.setattr(main, "init_db", lambda: None)
    with TestClient(main.create_app()) as client:
        for path in ("/health", "/healthz"):
            assert client.get(path).json() == {"status": "ok"}
            assert client.head(path).status_code == 200
        for path in ("/", "/leer", "/manual"):
            assert client.head(path).status_code == 200


def test_engine_postgres_sin_conexiones_guardadas(monkeypatch):
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(
        database,
        "get_settings",
        lambda: type("S", (), {"database_url": "postgresql://u:p@localhost/db"})(),
    )
    engine = database.get_engine()
    assert isinstance(engine.pool, NullPool)
    monkeypatch.setattr(database, "_engine", None)
