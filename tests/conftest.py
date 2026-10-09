import pytest
from fastapi.testclient import TestClient

from scalper.api import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCALPER_TEST_MODE", "true")
    monkeypatch.setenv("SCALPER_DB_PATH", str(tmp_path / "scalper-test.sqlite3"))
    monkeypatch.delenv("SCALPER_API_TOKEN", raising=False)
    monkeypatch.delenv("SCALPER_ALPACA_PAPER_KEY", raising=False)
    monkeypatch.delenv("SCALPER_ALPACA_PAPER_SECRET", raising=False)
    monkeypatch.delenv("SCALPER_AUTOMATION_ENABLED", raising=False)
    monkeypatch.delenv("SCALPER_OLLAMA_MODEL", raising=False)
    with TestClient(app) as test_client:
        yield test_client
