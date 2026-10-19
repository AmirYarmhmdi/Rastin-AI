"""File guide.

- Use: Contains unit tests for health behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: External packages only: fastapi.testclient, and helpers.
"""

from fastapi.testclient import TestClient
from helpers import create_isolated_app
from sqlalchemy.exc import SQLAlchemyError

from rastin_ai.database.session import get_async_session


class FakeSession:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    async def execute(self, query) -> None:
        if self.error is not None:
            raise self.error


def override_session(session: FakeSession):
    async def dependency():
        yield session

    return dependency


# This checks the official health endpoint response.
def test_health_endpoint_returns_ok(monkeypatch) -> None:
    with TestClient(create_isolated_app(monkeypatch)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Rastin-AI",
        "version": "0.1.0",
        "environment": "development",
    }


def test_readiness_endpoint_returns_ready(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)
    app.dependency_overrides[get_async_session] = override_session(FakeSession())

    with TestClient(app) as client:
        response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_endpoint_returns_service_unavailable_on_database_failure(
    monkeypatch,
) -> None:
    app = create_isolated_app(monkeypatch)
    app.dependency_overrides[get_async_session] = override_session(
        FakeSession(error=SQLAlchemyError("database unavailable")),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable."}


# This checks that the optional root endpoint stays minimal and non-sensitive.
def test_root_endpoint_returns_minimal_service_metadata(monkeypatch) -> None:
    with TestClient(create_isolated_app(monkeypatch)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "Rastin-AI",
        "version": "0.1.0",
    }


# This checks that the app can be created without external services.
def test_application_can_be_created_without_external_services(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)

    assert app.title == "Rastin-AI"
