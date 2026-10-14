from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import Conflict, NotFound, register_error_handlers


def _client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/conflict")
    def conflict() -> None:
        raise Conflict("Idempotency key reused with a different payload", {"key": "k1"})

    @app.get("/missing")
    def missing() -> None:
        raise NotFound("PO not found")

    @app.get("/items/{item_id}")
    def item(item_id: int) -> None:
        return None

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def test_app_error_maps_to_status_and_error_envelope() -> None:
    response = _client().get("/conflict")
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "conflict",
            "message": "Idempotency key reused with a different payload",
            "details": {"key": "k1"},
        }
    }


def test_not_found_maps_to_404() -> None:
    response = _client().get("/missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_unexpected_error_is_500_without_leaking_internals() -> None:
    response = _client().get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text


def test_request_validation_error_uses_the_envelope() -> None:
    response = _client().get("/items/not-a-number")
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_failed"
    assert body["details"]["errors"][0]["loc"] == ["path", "item_id"]
