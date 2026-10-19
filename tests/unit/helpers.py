"""File guide.

- Use: Contains unit tests for helpers behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: External packages only: importlib, and sys.
"""

import importlib
import sys
from types import ModuleType

# These are the settings variables that can affect the Phase 3 app.
SETTINGS_ENV_VARS = (
    "APP_NAME",
    "APP_VERSION",
    "ENVIRONMENT",
    "DEBUG",
    "API_V1_PREFIX",
    "LOG_LEVEL",
    "HOST",
    "PORT",
    "DATABASE_URL",
    "OPENAI_API_KEY",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_COLLECTION_NAME",
    "OPENAI_PLANNER_MODEL",
    "OPENAI_RESPONSE_MODEL",
    "OPENAI_EMBEDDING_MODEL",
    "RASTIN_AI_TOOL_SELECTOR_MODEL",
    "RAG_EMBEDDING_DIMENSION",
    "RAG_CHUNK_SIZE",
    "RAG_CHUNK_OVERLAP",
    "RAG_RETRIEVAL_TOP_K",
    "RAG_CONTEXT_MAX_CHARS",
    "CONVERSATION_HISTORY_MAX_TURNS",
    "CONVERSATION_HISTORY_MAX_CHARS",
    "EVALUATION_MODEL",
    "EVALUATION_EMBEDDING_MODEL",
    "EVALUATION_ANSWER_RELEVANCY_THRESHOLD",
    "EVALUATION_FAITHFULNESS_THRESHOLD",
    "EVALUATION_CONTEXT_PRECISION_THRESHOLD",
    "EVALUATION_CONTEXT_RECALL_THRESHOLD",
    "EVALUATION_HALLUCINATION_THRESHOLD",
    "LANGFUSE_HOST",
    "LANGFUSE_ENABLED",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_BASE_URL",
    "LOCAL_STORAGE_ROOT",
    "STORAGE_BACKEND",
    "MAX_UPLOAD_BYTES",
    "AZURE_STORAGE_ACCOUNT_NAME",
    "AZURE_STORAGE_CONTAINER_NAME",
    "AZURE_STORAGE_MANAGED_IDENTITY_CLIENT_ID",
    "AUTH_MODE",
    "AUTH_DISABLED_LOCAL_USER_ISSUER",
    "AUTH_DISABLED_LOCAL_USER_SUBJECT",
    "AUTH_DISABLED_LOCAL_USER_EMAIL",
    "AUTH_DISABLED_LOCAL_USER_DISPLAY_NAME",
    "AUTH_DEV_JWT_ISSUER",
    "AUTH_DEV_JWT_AUDIENCE",
    "AUTH_DEV_JWT_SECRET",
    "AUTH_DEV_JWT_ALGORITHM",
    "AUTH_OIDC_ISSUER",
    "AUTH_OIDC_AUDIENCE",
    "AUTH_OIDC_JWKS_URL",
    "AUTH_OIDC_JWKS_JSON",
    "AUTH_OIDC_ALGORITHMS",
    "CORS_ALLOWED_ORIGINS",
    "CORS_ALLOW_CREDENTIALS",
    "EXPOSE_INTERNAL_STORAGE_DEBUG",
)


# This removes app settings from the test environment and clears the settings cache.
def clear_settings_env(monkeypatch) -> None:
    for env_var in SETTINGS_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)

    from rastin_ai.core.config import get_settings

    get_settings.cache_clear()


def _remove_module(module_name: str) -> None:
    sys.modules.pop(module_name, None)

    package_name, _, child_name = module_name.rpartition(".")
    package = sys.modules.get(package_name)
    if isinstance(package, ModuleType) and hasattr(package, child_name):
        delattr(package, child_name)


# This creates a fresh app that is not affected by the developer shell.
def create_isolated_app(monkeypatch):
    clear_settings_env(monkeypatch)

    from rastin_ai.api import dependencies
    from rastin_ai.database.engine import get_engine
    from rastin_ai.database.session import get_session_factory

    dependencies._get_local_storage_provider.cache_clear()
    dependencies._get_azure_blob_storage_provider.cache_clear()
    get_session_factory.cache_clear()
    get_engine.cache_clear()

    # Remove imported app modules so they reload with clean settings.
    for module_name in (
        "rastin_ai.main",
        "rastin_ai.api.router",
        "rastin_ai.api.v1.router",
        "rastin_ai.api.v1.endpoints.documents",
        "rastin_ai.api.v1.endpoints.health",
        "rastin_ai.api.v1.endpoints.messages",
        "rastin_ai.api.v1.endpoints.organizations",
        "rastin_ai.api.v1.endpoints.project_documents",
        "rastin_ai.api.v1.endpoints.project_sessions",
        "rastin_ai.api.v1.endpoints.projects",
        "rastin_ai.api.v1.endpoints.questions",
        "rastin_ai.api.v1.endpoints.sessions",
        "rastin_ai.api.v1.endpoints.workflows",
        "rastin_ai.api.dependencies",
    ):
        _remove_module(module_name)

    # Import the main module again and build a fresh FastAPI app.
    main = importlib.import_module("rastin_ai.main")
    return main.create_app()
