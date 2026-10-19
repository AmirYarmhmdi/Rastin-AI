"""File guide.

- Use: Contains unit tests for exceptions behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.core.exceptions.
"""

from fastapi import status
from fastapi.testclient import TestClient
from helpers import create_isolated_app

from rastin_ai.core.exceptions import AppException


# This checks the response for expected application errors.
def test_app_exception_returns_error_payload(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)

    # Add a temporary route that raises our custom application error.
    @app.get("/app-error")
    def raise_app_exception() -> None:
        raise AppException(
            "Readable problem",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="TEST_ERROR",
            details={"field": "value"},
        )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/app-error")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "TEST_ERROR",
            "message": "Readable problem",
            "details": {"field": "value"},
        }
    }


# This checks that unexpected errors do not leak internal details.
def test_unexpected_exception_returns_safe_error_payload(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)

    # Add a temporary route that raises a normal Python error.
    @app.get("/boom")
    def raise_unexpected_exception() -> None:
        raise RuntimeError("secret internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    payload = response.json()

    assert response.status_code == 500
    assert payload == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected internal error occurred.",
            "details": None,
        }
    }
    assert "secret internal detail" not in str(payload)
    assert "Traceback" not in str(payload)
