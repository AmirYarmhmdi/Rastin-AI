"""File guide.

- Use: Contains unit tests for settings behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.core.config.
"""

import pytest
from helpers import clear_settings_env
from pydantic import ValidationError

from rastin_ai.core.config import (
    ConfigurationError,
    Settings,
    safe_configuration_summary,
    validate_runtime_configuration,
    validate_startup_configuration,
)


def build_test_settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)


# This checks that normal DEBUG boolean values are accepted.
@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("true", True),
        ("false", False),
        ("1", True),
        ("0", False),
    ),
)
def test_debug_accepts_standard_boolean_values(monkeypatch, value, expected) -> None:
    clear_settings_env(monkeypatch)

    assert build_test_settings(DEBUG=value).DEBUG is expected


# This checks that invalid DEBUG values fail instead of being hidden.
@pytest.mark.parametrize("value", ("release", "random-value"))
def test_debug_rejects_invalid_values(monkeypatch, value) -> None:
    clear_settings_env(monkeypatch)

    with pytest.raises(ValidationError):
        build_test_settings(DEBUG=value)


# This checks that environment variables can override default settings.
def test_environment_variables_override_defaults(monkeypatch) -> None:
    clear_settings_env(monkeypatch)
    monkeypatch.setenv("APP_NAME", "AuditName")
    monkeypatch.setenv("ENVIRONMENT", "audit")

    settings = build_test_settings()

    assert settings.APP_NAME == "AuditName"
    assert settings.ENVIRONMENT == "audit"


def test_local_storage_root_has_development_default(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    settings = build_test_settings()

    assert settings.STORAGE_BACKEND == "local"
    assert settings.LOCAL_STORAGE_ROOT == "storage"
    assert settings.MAX_UPLOAD_BYTES == 10 * 1024 * 1024
    assert settings.AZURE_STORAGE_ACCOUNT_NAME is None
    assert settings.AZURE_STORAGE_CONTAINER_NAME is None
    assert settings.AZURE_STORAGE_MANAGED_IDENTITY_CLIENT_ID is None


def test_runtime_configuration_overrides_storage_backend_and_secrets(
    monkeypatch,
) -> None:
    clear_settings_env(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "azure_blob")
    monkeypatch.setenv("OPENAI_API_KEY", "runtime-openai-key")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://runtime-db")
    monkeypatch.setenv("QDRANT_API_KEY", "runtime-qdrant-key")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "runtime-langfuse-secret")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_NAME", "rastinaistorage")
    monkeypatch.setenv("AZURE_STORAGE_CONTAINER_NAME", "rastin-ai-files")
    monkeypatch.setenv(
        "AZURE_STORAGE_MANAGED_IDENTITY_CLIENT_ID",
        "11111111-1111-4111-8111-111111111111",
    )

    settings = build_test_settings()

    assert settings.STORAGE_BACKEND == "azure_blob"
    assert settings.OPENAI_API_KEY == "runtime-openai-key"
    assert settings.DATABASE_URL == "postgresql+asyncpg://runtime-db"
    assert settings.QDRANT_API_KEY == "runtime-qdrant-key"
    assert settings.LANGFUSE_SECRET_KEY == "runtime-langfuse-secret"
    assert settings.AZURE_STORAGE_ACCOUNT_NAME == "rastinaistorage"
    assert settings.AZURE_STORAGE_CONTAINER_NAME == "rastin-ai-files"
    assert (
        settings.AZURE_STORAGE_MANAGED_IDENTITY_CLIENT_ID
        == "11111111-1111-4111-8111-111111111111"
    )


def test_rag_settings_have_development_defaults(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    settings = build_test_settings()

    assert settings.QDRANT_COLLECTION_NAME == "rastin_ai_rag_chunks"
    assert settings.OPENAI_PLANNER_MODEL == "gpt-4o-mini"
    assert settings.OPENAI_RESPONSE_MODEL == "gpt-4o-mini"
    assert settings.OPENAI_EMBEDDING_MODEL == "text-embedding-3-small"
    assert settings.RASTIN_AI_TOOL_SELECTOR_MODEL == "gpt-4.1-mini"
    assert settings.RAG_EMBEDDING_DIMENSION == 1536
    assert settings.RAG_CHUNK_SIZE == 800
    assert settings.RAG_CHUNK_OVERLAP == 100
    assert settings.RAG_RETRIEVAL_TOP_K == 5
    assert settings.RAG_CONTEXT_MAX_CHARS == 12000
    assert settings.CONVERSATION_HISTORY_MAX_TURNS == 6
    assert settings.CONVERSATION_HISTORY_MAX_CHARS == 4000


def test_openai_model_settings_can_be_overridden(monkeypatch) -> None:
    clear_settings_env(monkeypatch)
    monkeypatch.setenv("OPENAI_PLANNER_MODEL", "planner-test-model")
    monkeypatch.setenv("OPENAI_RESPONSE_MODEL", "response-test-model")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "embedding-test-model")

    settings = build_test_settings()

    assert settings.OPENAI_PLANNER_MODEL == "planner-test-model"
    assert settings.OPENAI_RESPONSE_MODEL == "response-test-model"
    assert settings.OPENAI_EMBEDDING_MODEL == "embedding-test-model"


def test_evaluation_settings_have_baseline_defaults(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    settings = build_test_settings()

    assert settings.EVALUATION_MODEL == "gpt-4.1-mini"
    assert settings.EVALUATION_EMBEDDING_MODEL == "text-embedding-3-small"
    assert settings.EVALUATION_ANSWER_RELEVANCY_THRESHOLD == 0.70
    assert settings.EVALUATION_FAITHFULNESS_THRESHOLD == 0.70
    assert settings.EVALUATION_CONTEXT_PRECISION_THRESHOLD == 0.70
    assert settings.EVALUATION_CONTEXT_RECALL_THRESHOLD == 0.70
    assert settings.EVALUATION_HALLUCINATION_THRESHOLD == 0.30


def test_langfuse_observability_is_disabled_by_default(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    settings = build_test_settings()

    assert settings.LANGFUSE_ENABLED is False
    assert settings.LANGFUSE_PUBLIC_KEY is None
    assert settings.LANGFUSE_SECRET_KEY is None
    assert settings.LANGFUSE_BASE_URL is None


def test_valid_local_storage_configuration_passes_startup_validation(
    monkeypatch,
) -> None:
    clear_settings_env(monkeypatch)

    settings = build_test_settings(
        STORAGE_BACKEND="local",
        LOCAL_STORAGE_ROOT="storage",
        LANGFUSE_ENABLED=False,
    )

    validate_startup_configuration(settings)


def test_valid_azure_blob_managed_identity_configuration_passes_startup_validation(
    monkeypatch,
) -> None:
    clear_settings_env(monkeypatch)

    settings = build_test_settings(
        STORAGE_BACKEND="azure_blob",
        AZURE_STORAGE_ACCOUNT_NAME="rastinaistorage",
        AZURE_STORAGE_CONTAINER_NAME="documents",
        AZURE_STORAGE_MANAGED_IDENTITY_CLIENT_ID=None,
    )

    validate_startup_configuration(settings)


@pytest.mark.parametrize(
    "missing_setting",
    ("AZURE_STORAGE_ACCOUNT_NAME", "AZURE_STORAGE_CONTAINER_NAME"),
)
def test_missing_required_azure_storage_settings_fail_startup_validation(
    monkeypatch,
    missing_setting: str,
) -> None:
    clear_settings_env(monkeypatch)
    values = {
        "STORAGE_BACKEND": "azure_blob",
        "AZURE_STORAGE_ACCOUNT_NAME": "rastinaistorage",
        "AZURE_STORAGE_CONTAINER_NAME": "documents",
    }
    values[missing_setting] = None

    with pytest.raises(ConfigurationError) as exc_info:
        validate_startup_configuration(build_test_settings(**values))

    assert missing_setting in str(exc_info.value)


def test_unknown_storage_backend_is_rejected_by_settings_validation(
    monkeypatch,
) -> None:
    clear_settings_env(monkeypatch)

    with pytest.raises(ValidationError):
        build_test_settings(STORAGE_BACKEND="s3")


def test_langfuse_disabled_does_not_require_credentials(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    settings = build_test_settings(
        LANGFUSE_ENABLED=False,
        LANGFUSE_PUBLIC_KEY=None,
        LANGFUSE_SECRET_KEY=None,
    )

    validate_startup_configuration(settings)


def test_production_environment_requires_oidc_auth(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    with pytest.raises(ConfigurationError) as exc_info:
        validate_startup_configuration(
            build_test_settings(ENVIRONMENT="production", AUTH_MODE="disabled")
        )

    assert "AUTH_MODE" in str(exc_info.value)


def test_production_environment_rejects_internal_storage_debug(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    with pytest.raises(ConfigurationError) as exc_info:
        validate_startup_configuration(
            build_test_settings(
                ENVIRONMENT="production",
                AUTH_MODE="oidc",
                AUTH_OIDC_ISSUER="https://issuer.example.test",
                AUTH_OIDC_AUDIENCE="rastin_ai",
                AUTH_OIDC_JWKS_JSON='{"keys":[]}',
                EXPOSE_INTERNAL_STORAGE_DEBUG=True,
            )
        )

    assert "EXPOSE_INTERNAL_STORAGE_DEBUG" in str(exc_info.value)


def test_dev_jwt_auth_requires_validation_settings(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    with pytest.raises(ConfigurationError) as exc_info:
        validate_startup_configuration(build_test_settings(AUTH_MODE="dev_jwt"))

    message = str(exc_info.value)
    assert "AUTH_DEV_JWT_ISSUER" in message
    assert "AUTH_DEV_JWT_AUDIENCE" in message
    assert "AUTH_DEV_JWT_SECRET" in message


def test_oidc_auth_requires_jwks_source(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    with pytest.raises(ConfigurationError) as exc_info:
        validate_startup_configuration(
            build_test_settings(
                AUTH_MODE="oidc",
                AUTH_OIDC_ISSUER="https://issuer.example.test",
                AUTH_OIDC_AUDIENCE="rastin_ai",
            )
        )

    assert "AUTH_OIDC_JWKS_URL" in str(exc_info.value)


def test_cors_wildcard_cannot_be_used_with_credentials(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    with pytest.raises(ConfigurationError) as exc_info:
        validate_startup_configuration(
            build_test_settings(
                CORS_ALLOWED_ORIGINS="*,https://app.example.test",
                CORS_ALLOW_CREDENTIALS=True,
            )
        )

    assert "CORS_ALLOWED_ORIGINS" in str(exc_info.value)


@pytest.mark.parametrize(
    "missing_setting",
    ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"),
)
def test_langfuse_enabled_requires_both_project_keys(
    monkeypatch,
    missing_setting: str,
) -> None:
    clear_settings_env(monkeypatch)
    values = {
        "LANGFUSE_ENABLED": True,
        "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
        "LANGFUSE_SECRET_KEY": "sk-lf-test",
    }
    values[missing_setting] = None

    with pytest.raises(ConfigurationError) as exc_info:
        validate_startup_configuration(build_test_settings(**values))

    assert missing_setting in str(exc_info.value)


def test_runtime_configuration_requires_external_service_settings(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    with pytest.raises(ConfigurationError) as exc_info:
        validate_runtime_configuration(
            build_test_settings(
                DATABASE_URL=None,
                QDRANT_URL=None,
                OPENAI_API_KEY=None,
            )
        )

    message = str(exc_info.value)
    assert "DATABASE_URL" in message
    assert "QDRANT_URL" in message
    assert "OPENAI_API_KEY" in message


def test_validation_errors_and_summary_do_not_expose_secret_values(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    settings = build_test_settings(
        STORAGE_BACKEND="azure_blob",
        AZURE_STORAGE_ACCOUNT_NAME=None,
        AZURE_STORAGE_CONTAINER_NAME=None,
        OPENAI_API_KEY="sk-secret-openai-value",
        QDRANT_API_KEY="qdrant-secret-value",
        DATABASE_URL="postgresql+asyncpg://user:secret-password@db/rastin_ai",
        LANGFUSE_ENABLED=True,
        LANGFUSE_PUBLIC_KEY="pk-lf-test",
        LANGFUSE_SECRET_KEY=None,
    )

    with pytest.raises(ConfigurationError) as exc_info:
        validate_startup_configuration(settings)

    rendered = str(exc_info.value)
    assert "sk-secret-openai-value" not in rendered
    assert "qdrant-secret-value" not in rendered
    assert "secret-password" not in rendered
    summary = safe_configuration_summary(settings)
    assert "sk-secret-openai-value" not in str(summary)
    assert "qdrant-secret-value" not in str(summary)
    assert "secret-password" not in str(summary)
    assert summary["openai_configured"] is True
    assert summary["qdrant_api_key_configured"] is True
