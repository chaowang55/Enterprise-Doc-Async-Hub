import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_engine, init_db


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("API_TOKEN", "")
    get_settings.cache_clear()
    get_engine.cache_clear()
    init_db()
    yield tmp_path
    get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def client(environment):
    from app.main import app

    with TestClient(app) as client:
        yield client
