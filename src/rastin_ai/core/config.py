"""File guide.

- Use: Loads application settings from environment variables and .env files.
- Usage: Import Settings, and get_settings from rastin_ai.core.config.
- Duties: Defines Settings, and get_settings and related helper logic.
- Depends on: External packages only: functools, pydantic, and pydantic_settings.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

STORAGE_BACKENDS = frozenset(("local", "azure_blob"))
AUTH_MODES = frozenset(("disabled", "dev_jwt", "oidc"))
NON_PRODUCTION_ENVIRONMENTS = frozenset(("development", "dev", "local", "test"))


# This class defines all settings the backend needs.
class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env."""

    # These defaults let the app run locally without a .env file.
    APP_NAME: str = "Rastin-AI"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DATABASE_URL: str | None = None
    OPENAI_API_KEY: str | None = None
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_NAME: str = "rastin_ai_rag_chunks"
    OPENAI_PLANNER_MODEL: str = "gpt-4o-mini"
    OPENAI_RESPONSE_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    RASTIN_AI_TOOL_SELECTOR_MODEL: str = "gpt-4.1-mini"
    RAG_EMBEDDING_DIMENSION: int = Field(default=1536, ge=1)
    RAG_CHUNK_SIZE: int = Field(default=800, ge=1)
    RAG_CHUNK_OVERLAP: int = Field(default=100, ge=0)
    RAG_RETRIEVAL_TOP_K: int = Field(default=5, ge=1)
    RAG_CONTEXT_MAX_CHARS: int = Field(default=12_000, ge=1)
    CONVERSATION_HISTORY_MAX_TURNS: int = Field(default=6, ge=0)
    CONVERSATION_HISTORY_MAX_CHARS: int = Field(default=4_000, ge=1)
    EVALUATION_MODEL: str = "gpt-4.1-mini"
    EVALUATION_EMBEDDING_MODEL: str = "text-embedding-3-small"
    EVALUATION_ANSWER_RELEVANCY_THRESHOLD: float = Field(default=0.70, ge=0.0, le=1.0)
    EVALUATION_FAITHFULNESS_THRESHOLD: float = Field(default=0.70, ge=0.0, le=1.0)
    EVALUATION_CONTEXT_PRECISION_THRESHOLD: float = Field(default=0.70, ge=0.0, le=1.0)
    EVALUATION_CONTEXT_RECALL_THRESHOLD: float = Field(default=0.70, ge=0.0, le=1.0)
    EVALUATION_HALLUCINATION_THRESHOLD: float = Field(default=0.30, ge=0.0, le=1.0)
    LANGFUSE_HOST: str | None = None
    LANGFUSE_ENABLED: bool = False
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_BASE_URL: str | None = None
    LOCAL_STORAGE_ROOT: str = "storage"
    STORAGE_BACKEND: Literal["local", "azure_blob"] = "local"
    MAX_UPLOAD_BYTES: int = Field(default=10 * 1024 * 1024, ge=1)
    AZURE_STORAGE_ACCOUNT_NAME: str | None = None
    AZURE_STORAGE_CONTAINER_NAME: str | None = None
    AZURE_STORAGE_MANAGED_IDENTITY_CLIENT_ID: str | None = None
    AUTH_MODE: Literal["disabled", "dev_jwt", "oidc"] = "disabled"
    AUTH_DISABLED_LOCAL_USER_ISSUER: str = "rastin-ai.local"
    AUTH_DISABLED_LOCAL_USER_SUBJECT: str = "local-development-user"
    AUTH_DISABLED_LOCAL_USER_EMAIL: str | None = "local@rastin-ai.dev"
    AUTH_DISABLED_LOCAL_USER_DISPLAY_NAME: str | None = "Local Development User"
    AUTH_DEV_JWT_ISSUER: str | None = None
    AUTH_DEV_JWT_AUDIENCE: str | None = None
    AUTH_DEV_JWT_SECRET: str | None = None
    AUTH_DEV_JWT_ALGORITHM: str = "HS256"
    AUTH_OIDC_ISSUER: str | None = None
    AUTH_OIDC_AUDIENCE: str | None = None
    AUTH_OIDC_JWKS_URL: str | None = None
    AUTH_OIDC_JWKS_JSON: str | None = None
    AUTH_OIDC_ALGORITHMS: str = "RS256"
    CORS_ALLOWED_ORIGINS: str = ""
    CORS_ALLOW_CREDENTIALS: bool = False
    EXPOSE_INTERNAL_STORAGE_DEBUG: bool = False

    # This tells pydantic-settings to also read values from a local .env file.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@dataclass(frozen=True)
class ConfigurationIssue:
    """A safe configuration validation issue that never includes secret values."""

    setting: str
    message: str


class ConfigurationError(RuntimeError):
    """Raised when startup/runtime configuration is invalid."""

    def __init__(self, issues: list[ConfigurationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(_format_configuration_issues(issues))


def validate_startup_configuration(settings: Settings) -> None:
    """Validate configuration combinations that should fail application startup."""
    issues = collect_configuration_issues(
        settings,
        require_external_services=False,
    )
    if issues:
        raise ConfigurationError(issues)


def validate_runtime_configuration(settings: Settings) -> None:
    """Validate the full document/RAG runtime dependency contract."""
    issues = collect_configuration_issues(
        settings,
        require_external_services=True,
    )
    if issues:
        raise ConfigurationError(issues)


def collect_configuration_issues(
    settings: Settings,
    *,
    require_external_services: bool,
) -> list[ConfigurationIssue]:
    """Return safe configuration issues for the selected validation level."""
    issues: list[ConfigurationIssue] = []

    if settings.STORAGE_BACKEND not in STORAGE_BACKENDS:
        issues.append(
            ConfigurationIssue(
                "STORAGE_BACKEND",
                "must be one of: azure_blob, local.",
            )
        )
    elif settings.STORAGE_BACKEND == "local":
        if not _has_text(settings.LOCAL_STORAGE_ROOT):
            issues.append(
                ConfigurationIssue(
                    "LOCAL_STORAGE_ROOT",
                    "is required when STORAGE_BACKEND=local.",
                )
            )
    elif settings.STORAGE_BACKEND == "azure_blob":
        _require_text(
            issues,
            settings.AZURE_STORAGE_ACCOUNT_NAME,
            "AZURE_STORAGE_ACCOUNT_NAME",
            "is required when STORAGE_BACKEND=azure_blob.",
        )
        _require_text(
            issues,
            settings.AZURE_STORAGE_CONTAINER_NAME,
            "AZURE_STORAGE_CONTAINER_NAME",
            "is required when STORAGE_BACKEND=azure_blob.",
        )

    if settings.AUTH_MODE not in AUTH_MODES:
        issues.append(
            ConfigurationIssue(
                "AUTH_MODE",
                "must be one of: disabled, dev_jwt, oidc.",
            )
        )
    elif settings.AUTH_MODE == "dev_jwt":
        _require_text(
            issues,
            settings.AUTH_DEV_JWT_ISSUER,
            "AUTH_DEV_JWT_ISSUER",
            "is required when AUTH_MODE=dev_jwt.",
        )
        _require_text(
            issues,
            settings.AUTH_DEV_JWT_AUDIENCE,
            "AUTH_DEV_JWT_AUDIENCE",
            "is required when AUTH_MODE=dev_jwt.",
        )
        _require_text(
            issues,
            settings.AUTH_DEV_JWT_SECRET,
            "AUTH_DEV_JWT_SECRET",
            "is required when AUTH_MODE=dev_jwt.",
        )
        _require_text(
            issues,
            settings.AUTH_DEV_JWT_ALGORITHM,
            "AUTH_DEV_JWT_ALGORITHM",
            "is required when AUTH_MODE=dev_jwt.",
        )
    elif settings.AUTH_MODE == "oidc":
        _require_text(
            issues,
            settings.AUTH_OIDC_ISSUER,
            "AUTH_OIDC_ISSUER",
            "is required when AUTH_MODE=oidc.",
        )
        _require_text(
            issues,
            settings.AUTH_OIDC_AUDIENCE,
            "AUTH_OIDC_AUDIENCE",
            "is required when AUTH_MODE=oidc.",
        )
        if not _has_text(settings.AUTH_OIDC_JWKS_URL) and not _has_text(
            settings.AUTH_OIDC_JWKS_JSON
        ):
            issues.append(
                ConfigurationIssue(
                    "AUTH_OIDC_JWKS_URL",
                    "or AUTH_OIDC_JWKS_JSON is required when AUTH_MODE=oidc.",
                )
            )

    if _is_production_environment(settings):
        if settings.AUTH_MODE in {"disabled", "dev_jwt"}:
            issues.append(
                ConfigurationIssue(
                    "AUTH_MODE",
                    "must be oidc in production-like environments.",
                )
            )
        if settings.EXPOSE_INTERNAL_STORAGE_DEBUG:
            issues.append(
                ConfigurationIssue(
                    "EXPOSE_INTERNAL_STORAGE_DEBUG",
                    "must be false in production-like environments.",
                )
            )

    if settings.CORS_ALLOW_CREDENTIALS and "*" in cors_allowed_origins(settings):
        issues.append(
            ConfigurationIssue(
                "CORS_ALLOWED_ORIGINS",
                "must not include * when CORS_ALLOW_CREDENTIALS=true.",
            )
        )

    _require_text(
        issues,
        settings.QDRANT_COLLECTION_NAME,
        "QDRANT_COLLECTION_NAME",
        "must not be empty.",
    )
    _require_text(
        issues,
        settings.OPENAI_PLANNER_MODEL,
        "OPENAI_PLANNER_MODEL",
        "must not be empty.",
    )
    _require_text(
        issues,
        settings.OPENAI_RESPONSE_MODEL,
        "OPENAI_RESPONSE_MODEL",
        "must not be empty.",
    )
    _require_text(
        issues,
        settings.OPENAI_EMBEDDING_MODEL,
        "OPENAI_EMBEDDING_MODEL",
        "must not be empty.",
    )
    _require_text(
        issues,
        settings.RASTIN_AI_TOOL_SELECTOR_MODEL,
        "RASTIN_AI_TOOL_SELECTOR_MODEL",
        "must not be empty.",
    )
    if settings.RAG_CHUNK_OVERLAP >= settings.RAG_CHUNK_SIZE:
        issues.append(
            ConfigurationIssue(
                "RAG_CHUNK_OVERLAP",
                "must be smaller than RAG_CHUNK_SIZE.",
            )
        )

    if settings.LANGFUSE_ENABLED:
        _require_text(
            issues,
            settings.LANGFUSE_PUBLIC_KEY,
            "LANGFUSE_PUBLIC_KEY",
            "is required when LANGFUSE_ENABLED=true.",
        )
        _require_text(
            issues,
            settings.LANGFUSE_SECRET_KEY,
            "LANGFUSE_SECRET_KEY",
            "is required when LANGFUSE_ENABLED=true.",
        )

    if require_external_services:
        _require_text(
            issues,
            settings.DATABASE_URL,
            "DATABASE_URL",
            "is required for PostgreSQL-backed runtime workflows.",
        )
        _require_text(
            issues,
            settings.QDRANT_URL,
            "QDRANT_URL",
            "is required for document indexing and RAG retrieval.",
        )
        _require_text(
            issues,
            settings.OPENAI_API_KEY,
            "OPENAI_API_KEY",
            "is required for embeddings, planning, and response generation.",
        )

    return issues


def safe_configuration_summary(settings: Settings) -> dict[str, object]:
    """Return loggable non-secret configuration diagnostics."""
    return {
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "storage_backend": settings.STORAGE_BACKEND,
        "database_configured": _has_text(settings.DATABASE_URL),
        "qdrant_configured": _has_text(settings.QDRANT_URL),
        "qdrant_api_key_configured": _has_text(settings.QDRANT_API_KEY),
        "openai_configured": _has_text(settings.OPENAI_API_KEY),
        "langfuse_enabled": settings.LANGFUSE_ENABLED,
        "langfuse_configured": _has_text(settings.LANGFUSE_PUBLIC_KEY)
        and _has_text(settings.LANGFUSE_SECRET_KEY),
        "auth_mode": settings.AUTH_MODE,
        "cors_origin_count": len(cors_allowed_origins(settings)),
        "azure_storage_account_configured": _has_text(
            settings.AZURE_STORAGE_ACCOUNT_NAME
        ),
        "azure_storage_container_configured": _has_text(
            settings.AZURE_STORAGE_CONTAINER_NAME
        ),
        "azure_user_assigned_identity_configured": _has_text(
            settings.AZURE_STORAGE_MANAGED_IDENTITY_CLIENT_ID
        ),
    }


def application_setting_names() -> tuple[str, ...]:
    """Return the canonical environment variable names consumed by the app."""
    return tuple(Settings.model_fields)


def cors_allowed_origins(settings: Settings) -> list[str]:
    """Return configured CORS origins as a normalized list."""
    return [
        origin.strip()
        for origin in settings.CORS_ALLOWED_ORIGINS.split(",")
        if origin.strip()
    ]


def _is_production_environment(settings: Settings) -> bool:
    return settings.ENVIRONMENT.strip().lower() not in NON_PRODUCTION_ENVIRONMENTS


def _require_text(
    issues: list[ConfigurationIssue],
    value: str | None,
    setting: str,
    message: str,
) -> None:
    if not _has_text(value):
        issues.append(ConfigurationIssue(setting, message))


def _has_text(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _format_configuration_issues(issues: list[ConfigurationIssue]) -> str:
    details = "; ".join(f"{issue.setting} {issue.message}" for issue in issues)
    return f"Invalid Rastin-AI configuration: {details}"


# This caches settings so the app does not rebuild them on every request.
@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
