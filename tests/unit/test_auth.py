"""Tests for Phase A authentication primitives and API protection."""

import importlib
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from helpers import _remove_module, clear_settings_env

from rastin_ai.core.config import Settings
from rastin_ai.security.auth import AuthenticationError, validate_bearer_token


@pytest.fixture(autouse=True)
def clean_settings_environment(monkeypatch):
    clear_settings_env(monkeypatch)


def test_disabled_auth_returns_configured_local_identity() -> None:
    identity = validate_bearer_token(
        token=None,
        settings=Settings(
            _env_file=None,
            AUTH_MODE="disabled",
            AUTH_DISABLED_LOCAL_USER_ISSUER="local-issuer",
            AUTH_DISABLED_LOCAL_USER_SUBJECT="local-user",
            AUTH_DISABLED_LOCAL_USER_EMAIL="local@example.test",
            AUTH_DISABLED_LOCAL_USER_DISPLAY_NAME="Local User",
        ),
    )

    assert identity.issuer == "local-issuer"
    assert identity.subject == "local-user"
    assert identity.email == "local@example.test"
    assert identity.display_name == "Local User"


def test_dev_jwt_validates_standard_claims() -> None:
    settings = _dev_jwt_settings()
    token = _dev_token(subject="user-a", email="user-a@example.test")

    identity = validate_bearer_token(token=token, settings=settings)

    assert identity.issuer == "https://issuer.example.test"
    assert identity.subject == "user-a"
    assert identity.email == "user-a@example.test"


def test_dev_jwt_rejects_missing_token() -> None:
    try:
        validate_bearer_token(token=None, settings=_dev_jwt_settings())
    except AuthenticationError as exc:
        assert exc.status_code == 401
        assert exc.error_code == "AUTHENTICATION_REQUIRED"
    else:
        raise AssertionError("Expected authentication failure.")


def test_dev_jwt_rejects_unsigned_none_algorithm_token() -> None:
    token = jwt.encode(
        {
            "iss": "https://issuer.example.test",
            "aud": "rastin_ai",
            "sub": "user-a",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        key="",
        algorithm="none",
    )

    try:
        validate_bearer_token(token=token, settings=_dev_jwt_settings())
    except AuthenticationError:
        pass
    else:
        raise AssertionError("Expected unsigned token to be rejected.")


def test_data_endpoint_requires_auth_before_database(monkeypatch) -> None:
    clear_settings_env(monkeypatch)
    monkeypatch.setenv("AUTH_MODE", "dev_jwt")
    monkeypatch.setenv("AUTH_DEV_JWT_ISSUER", "https://issuer.example.test")
    monkeypatch.setenv("AUTH_DEV_JWT_AUDIENCE", "rastin_ai")
    monkeypatch.setenv("AUTH_DEV_JWT_SECRET", "dev-secret-with-at-least-32-bytes")

    for module_name in (
        "rastin_ai.main",
        "rastin_ai.api.dependencies",
        "rastin_ai.api.router",
        "rastin_ai.api.v1.router",
        "rastin_ai.api.v1.endpoints.documents",
    ):
        _remove_module(module_name)

    app = importlib.import_module("rastin_ai.main").create_app()

    response = TestClient(app).get("/api/v1/documents")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def _dev_jwt_settings() -> Settings:
    return Settings(
        _env_file=None,
        AUTH_MODE="dev_jwt",
        AUTH_DEV_JWT_ISSUER="https://issuer.example.test",
        AUTH_DEV_JWT_AUDIENCE="rastin_ai",
        AUTH_DEV_JWT_SECRET="dev-secret-with-at-least-32-bytes",
    )


def _dev_token(*, subject: str, email: str | None = None) -> str:
    payload = {
        "iss": "https://issuer.example.test",
        "aud": "rastin_ai",
        "sub": subject,
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    if email is not None:
        payload["email"] = email
    return jwt.encode(payload, "dev-secret-with-at-least-32-bytes", algorithm="HS256")
