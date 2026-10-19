"""File guide.

- Use: Contains unit tests for database behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.core.config, rastin_ai.database,
  rastin_ai.database.engine, and rastin_ai.database.session.
"""

import asyncio
import importlib.util
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import alembic.context as alembic_context
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from helpers import clear_settings_env
from sqlalchemy.ext.asyncio import AsyncSession

from rastin_ai.core.config import Settings, get_settings
from rastin_ai.database import Base, models
from rastin_ai.database.engine import create_database_engine, get_database_url
from rastin_ai.database.session import create_session_factory

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_all_initial_models_are_registered_with_metadata() -> None:
    assert models.User.__tablename__ == "users"
    assert sorted(Base.metadata.tables) == [
        "conversation_message_documents",
        "conversation_messages",
        "documents",
        "file_metadata",
        "organization_members",
        "organizations",
        "project_members",
        "projects",
        "sessions",
        "users",
        "workflow_executions",
    ]


def test_metadata_uses_deterministic_naming_convention() -> None:
    assert Base.metadata.naming_convention == {
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }


def test_constraints_and_indexes_match_initial_schema() -> None:
    sessions = Base.metadata.tables["sessions"]
    documents = Base.metadata.tables["documents"]
    file_metadata = Base.metadata.tables["file_metadata"]
    users = Base.metadata.tables["users"]
    conversation_messages = Base.metadata.tables["conversation_messages"]
    conversation_message_documents = Base.metadata.tables[
        "conversation_message_documents"
    ]
    organizations = Base.metadata.tables["organizations"]
    organization_members = Base.metadata.tables["organization_members"]
    projects = Base.metadata.tables["projects"]
    project_members = Base.metadata.tables["project_members"]
    workflow_executions = Base.metadata.tables["workflow_executions"]

    assert {constraint.name for constraint in sessions.constraints} >= {
        "ck_sessions_session_project_scope_pair",
        "ck_sessions_session_status",
        "fk_sessions_organization_id_organizations",
        "fk_sessions_project_id_projects",
        "fk_sessions_user_id_users",
        "pk_sessions",
    }
    assert {index.name for index in sessions.indexes} == {
        "ix_sessions_organization_id",
        "ix_sessions_organization_id_project_id",
        "ix_sessions_project_id",
        "ix_sessions_project_user_updated_at",
        "ix_sessions_user_id",
    }
    assert sessions.c.organization_id.nullable is True
    assert sessions.c.project_id.nullable is True
    assert {index.name for index in documents.indexes} == {
        "ix_documents_organization_id",
        "ix_documents_organization_id_project_id",
        "ix_documents_project_id",
        "ix_documents_project_scope",
        "ix_documents_session_id",
        "ix_documents_user_id",
    }
    assert documents.c.session_id.nullable is True
    assert documents.c.user_id.nullable is True
    assert documents.c.organization_id.nullable is True
    assert documents.c.project_id.nullable is True
    assert documents.c.document_scope.server_default.arg == "LEGACY"
    assert documents.c.status.server_default.arg == "uploaded"
    assert documents.c.indexing_error_code.nullable is True
    assert documents.c.indexing_error_message.nullable is True
    assert {constraint.name for constraint in documents.constraints} >= {
        "ck_documents_document_scope",
        "ck_documents_document_scope_ownership",
        "ck_documents_document_status",
        "fk_documents_organization_id_organizations",
        "fk_documents_project_id_projects",
        "fk_documents_session_id_sessions",
        "fk_documents_user_id_users",
        "pk_documents",
    }
    assert file_metadata.c.document_id.unique is True
    assert file_metadata.c.document_id.nullable is True
    assert file_metadata.c.user_id.nullable is True
    assert file_metadata.c.normalized_extension.nullable is False
    assert file_metadata.c.status.nullable is False
    assert file_metadata.c.updated_at.nullable is False
    assert {constraint.name for constraint in file_metadata.constraints} >= {
        "ck_file_metadata_file_metadata_size_bytes_non_negative",
        "ck_file_metadata_file_metadata_status",
        "uq_file_metadata_document_id",
    }
    assert {index.name for index in workflow_executions.indexes} == {
        "ix_workflow_executions_organization_id",
        "ix_workflow_executions_organization_id_project_id",
        "ix_workflow_executions_project_id",
        "ix_workflow_executions_project_session_user",
        "ix_workflow_executions_session_id",
        "ix_workflow_executions_status",
        "ix_workflow_executions_user_id",
    }
    assert workflow_executions.c.user_id.nullable is True
    assert workflow_executions.c.organization_id.nullable is True
    assert workflow_executions.c.project_id.nullable is True
    assert workflow_executions.c.trace_id.nullable is True
    assert {constraint.name for constraint in workflow_executions.constraints} >= {
        "ck_workflow_executions_workflow_execution_project_scope_pair",
        "ck_workflow_executions_workflow_execution_status",
        "fk_workflow_executions_organization_id_organizations",
        "fk_workflow_executions_project_id_projects",
        "fk_workflow_executions_session_project_scope",
        "fk_workflow_executions_session_id_sessions",
        "pk_workflow_executions",
    }
    assert {constraint.name for constraint in users.constraints} >= {
        "pk_users",
        "uq_users_issuer_external_subject",
    }
    assert {index.name for index in users.indexes} >= {
        "ix_users_email",
        "ix_users_external_subject",
        "ix_users_issuer",
    }
    assert {constraint.name for constraint in conversation_messages.constraints} >= {
        "ck_conversation_messages_conversation_message_role",
        "ck_conversation_messages_conversation_message_status",
        "fk_conversation_messages_session_id_sessions",
        "fk_conversation_messages_workflow_id_workflow_executions",
        "pk_conversation_messages",
        "uq_conversation_messages_session_sequence",
    }
    assert {index.name for index in conversation_messages.indexes} == {
        "ix_conversation_messages_session_id",
        "ix_conversation_messages_workflow_id",
    }
    assert conversation_messages.c.citations.server_default.arg == "[]"
    assert conversation_messages.c.sources.server_default.arg == "[]"
    assert conversation_messages.c.message_metadata.server_default.arg == "{}"
    assert {
        constraint.name for constraint in conversation_message_documents.constraints
    } >= {
        (
            "ck_conversation_message_documents_"
            "conversation_message_document_reference_type"
        ),
        "fk_conversation_message_documents_document_id_documents",
        "fk_conversation_message_documents_file_metadata_id_file_metadata",
        "fk_conversation_message_documents_message_id_conversation_messages",
        "pk_conversation_message_documents",
    }
    assert {index.name for index in conversation_message_documents.indexes} == {
        "ix_conversation_message_documents_document_id",
        "ix_conversation_message_documents_file_metadata_id",
        "ix_conversation_message_documents_message_id",
    }
    assert {constraint.name for constraint in organizations.constraints} >= {
        "fk_organizations_created_by_user_id_users",
        "pk_organizations",
    }
    assert {index.name for index in organizations.indexes} >= {
        "ix_organizations_created_by_user_id",
        "ix_organizations_slug",
    }
    assert {constraint.name for constraint in organization_members.constraints} >= {
        "ck_organization_members_organization_member_role",
        "fk_organization_members_organization_id_organizations",
        "fk_organization_members_user_id_users",
        "pk_organization_members",
        "uq_organization_members_organization_id_user_id",
    }
    assert {index.name for index in organization_members.indexes} == {
        "ix_organization_members_organization_id",
        "ix_organization_members_user_id",
    }
    assert {constraint.name for constraint in projects.constraints} >= {
        "fk_projects_created_by_user_id_users",
        "fk_projects_organization_id_organizations",
        "pk_projects",
        "uq_projects_id_organization_id",
    }
    assert {index.name for index in projects.indexes} == {
        "ix_projects_created_by_user_id",
        "ix_projects_organization_id",
    }
    assert {constraint.name for constraint in project_members.constraints} >= {
        "ck_project_members_project_member_role",
        "fk_project_members_project_id_projects",
        "fk_project_members_user_id_users",
        "pk_project_members",
        "uq_project_members_project_id_user_id",
    }
    assert {index.name for index in project_members.indexes} == {
        "ix_project_members_project_id",
        "ix_project_members_user_id",
    }


def test_database_url_is_loaded_from_settings(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://rastin_ai:password@postgres/rastin_ai"
    )

    assert get_database_url(settings) == (
        "postgresql+asyncpg://rastin_ai:password@postgres/rastin_ai"
    )


def test_database_url_is_required_before_connecting(monkeypatch) -> None:
    clear_settings_env(monkeypatch)

    settings = Settings(DATABASE_URL=None)

    with pytest.raises(RuntimeError, match="DATABASE_URL must be set"):
        get_database_url(settings)


def test_alembic_ini_does_not_define_a_deployment_database_url() -> None:
    config = Config(PROJECT_ROOT / "alembic.ini")

    assert config.get_main_option("sqlalchemy.url") == ""


def test_alembic_revision_history_has_one_head() -> None:
    config = Config(PROJECT_ROOT / "alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["20260807_0009"]
    assert script.get_current_head() == "20260807_0009"


def test_project_document_scope_migration_preflight_rejects_null_legacy_sessions(
    monkeypatch,
) -> None:
    module = _load_migration("20260807_0008_project_document_scope.py")

    class FakeResult:
        def scalar_one(self) -> int:
            return 1

    class FakeBind:
        def execute(self, _statement: object) -> FakeResult:
            return FakeResult()

    monkeypatch.setattr(module.op, "get_bind", lambda: FakeBind())

    with pytest.raises(RuntimeError, match="NULL session_id"):
        module._assert_existing_documents_are_legacy_compatible()


def _load_migration(filename: str):
    spec = importlib.util.spec_from_file_location(
        f"_test_{filename.removesuffix('.py')}",
        PROJECT_ROOT / "alembic" / "versions" / filename,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def test_alembic_handles_percent_encoded_database_url_without_connecting(
    monkeypatch,
) -> None:
    database_url = "postgresql+asyncpg://rastin_ai:p%2Ass%25word@postgres/rastin_ai"
    offline_configure_kwargs = {}
    online_engine_config = {}

    class AlembicContextConfig:
        config_file_name = None

    @contextmanager
    def transaction() -> Iterator[None]:
        yield

    clear_settings_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    monkeypatch.setattr(
        alembic_context,
        "config",
        AlembicContextConfig(),
        raising=False,
    )
    monkeypatch.setattr(alembic_context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(
        alembic_context,
        "configure",
        lambda **kwargs: offline_configure_kwargs.update(kwargs),
    )
    monkeypatch.setattr(alembic_context, "begin_transaction", transaction)
    monkeypatch.setattr(alembic_context, "run_migrations", lambda: None)

    spec = importlib.util.spec_from_file_location(
        "_test_alembic_env",
        PROJECT_ROOT / "alembic" / "env.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
        get_settings.cache_clear()

    class FakeConnection:
        async def __aenter__(self) -> "FakeConnection":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def run_sync(self, _callable: object) -> None:
            pass

    class FakeEngine:
        def connect(self) -> FakeConnection:
            return FakeConnection()

        async def dispose(self) -> None:
            online_engine_config["disposed"] = True

    def fake_async_engine_from_config(
        section: dict[str, str],
        **_kwargs: object,
    ) -> FakeEngine:
        online_engine_config.update(section)
        return FakeEngine()

    module.config = Config()
    module.get_database_url = lambda: database_url
    module.async_engine_from_config = fake_async_engine_from_config

    asyncio.run(module.run_async_migrations())

    assert offline_configure_kwargs["url"] == database_url
    assert online_engine_config["sqlalchemy.url"] == database_url
    assert online_engine_config["disposed"] is True


def test_async_engine_and_session_factory_use_asyncpg_url() -> None:
    engine = create_database_engine(
        "postgresql+asyncpg://rastin_ai:password@localhost/rastin_ai"
    )
    session_factory = create_session_factory(engine)

    assert engine.url.drivername == "postgresql+asyncpg"
    assert session_factory.class_ is AsyncSession
    assert session_factory.kw["expire_on_commit"] is False

    asyncio.run(engine.dispose())
