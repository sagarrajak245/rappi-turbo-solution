from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_reports_ok_with_database_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'h.db').as_posix()}")
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "db_mode": "sqlite"}


def test_unknown_route_uses_error_envelope_shape() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
