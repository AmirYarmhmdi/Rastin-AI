"""Optional PostgreSQL integration coverage for project document persistence."""

import asyncio
import os
from uuid import UUID

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from rastin_ai.database import Base
from rastin_ai.database.engine import create_database_engine
from rastin_ai.database.enums import (
    ConversationSessionStatus,
    DocumentScope,
    OrganizationMemberRole,
    ProjectMemberRole,
)
from rastin_ai.database.models.conversation_session import ConversationSession
from rastin_ai.database.models.organization import Organization
from rastin_ai.database.models.organization_member import OrganizationMember
from rastin_ai.database.models.project import Project
from rastin_ai.database.models.project_member import ProjectMember
from rastin_ai.database.models.user import User
from rastin_ai.database.session import create_session_factory
from rastin_ai.repositories.project_documents import (
    ChatAttachmentCreate,
    ProjectDocumentCreate,
    SQLAlchemyProjectDocumentRepository,
)

TEST_DATABASE_URL = os.environ.get("RASTIN_AI_TEST_DATABASE_URL")
ORGANIZATION_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ORGANIZATION_ID = UUID("11111111-1111-4111-8111-111111111112")
PROJECT_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_PROJECT_ID = UUID("22222222-2222-4222-8222-222222222223")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
SESSION_ID = UUID("33333333-3333-4333-8333-333333333333")
LIBRARY_DOCUMENT_ID = UUID("44444444-4444-4444-8444-444444444444")
ATTACHMENT_DOCUMENT_ID = UUID("55555555-5555-4555-8555-555555555555")


def test_project_document_repository_enforces_join_scoped_metadata_access() -> None:
    if not TEST_DATABASE_URL:
        pytest.skip("RASTIN_AI_TEST_DATABASE_URL is required for this test.")
    if not _is_safe_test_database_url(TEST_DATABASE_URL):
        pytest.skip(
            "RASTIN_AI_TEST_DATABASE_URL must point to a database ending in _test.",
        )

    asyncio.run(_run_repository_test())


def _is_safe_test_database_url(database_url: str | None) -> bool:
    if not database_url:
        return False

    try:
        database_name = make_url(database_url).database
    except ArgumentError:
        return False

    return bool(database_name and database_name.endswith("_test"))


async def _run_repository_test() -> None:
    engine = create_database_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            await _seed_project(session)
            repository = SQLAlchemyProjectDocumentRepository(session)
            library = await repository.create_project_library_document(
                ProjectDocumentCreate(
                    document_id=LIBRARY_DOCUMENT_ID,
                    file_metadata_id=LIBRARY_DOCUMENT_ID,
                    organization_id=ORGANIZATION_ID,
                    project_id=PROJECT_ID,
                    uploaded_by_user_id=USER_ID,
                    original_filename="library.txt",
                    storage_key="organizations/org/projects/project/library/document",
                    storage_backend="local",
                    content_type="text/plain",
                    normalized_extension=".txt",
                    size_bytes=7,
                    checksum_sha256="1" * 64,
                )
            )
            attachment = await repository.create_chat_attachment_document(
                ChatAttachmentCreate(
                    document_id=ATTACHMENT_DOCUMENT_ID,
                    file_metadata_id=ATTACHMENT_DOCUMENT_ID,
                    organization_id=ORGANIZATION_ID,
                    project_id=PROJECT_ID,
                    uploaded_by_user_id=USER_ID,
                    session_id=SESSION_ID,
                    original_filename="attachment.txt",
                    storage_key="organizations/org/projects/project/chats/session/document",
                    storage_backend="local",
                    content_type="text/plain",
                    normalized_extension=".txt",
                    size_bytes=10,
                    checksum_sha256="2" * 64,
                )
            )
            scoped = await repository.get_project_library_document(
                LIBRARY_DOCUMENT_ID,
                organization_id=ORGANIZATION_ID,
                project_id=PROJECT_ID,
            )
            cross_project = await repository.get_project_library_document(
                LIBRARY_DOCUMENT_ID,
                organization_id=ORGANIZATION_ID,
                project_id=OTHER_PROJECT_ID,
            )
            cross_org = await repository.get_project_library_document(
                LIBRARY_DOCUMENT_ID,
                organization_id=OTHER_ORGANIZATION_ID,
                project_id=PROJECT_ID,
            )
            listed = await repository.list_project_library_documents(
                organization_id=ORGANIZATION_ID,
                project_id=PROJECT_ID,
            )

        assert library.document_scope == DocumentScope.PROJECT_LIBRARY.value
        assert library.session_id is None
        assert attachment.document_scope == DocumentScope.CHAT_ATTACHMENT.value
        assert attachment.session_id == SESSION_ID
        assert scoped is not None
        assert scoped.file_metadata_id == LIBRARY_DOCUMENT_ID
        assert cross_project is None
        assert cross_org is None
        assert [record.document_id for record in listed] == [LIBRARY_DOCUMENT_ID]
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def _seed_project(session) -> None:
    session.add(
        User(
            id=USER_ID,
            issuer="test",
            external_subject="project-documents-repository",
            email="project-documents-repository@example.test",
        )
    )
    session.add(
        Organization(
            id=ORGANIZATION_ID,
            name="Acme",
            slug="acme-project-documents",
            created_by_user_id=USER_ID,
        )
    )
    session.add(
        OrganizationMember(
            organization_id=ORGANIZATION_ID,
            user_id=USER_ID,
            role=OrganizationMemberRole.OWNER.value,
        )
    )
    session.add(
        Project(
            id=PROJECT_ID,
            organization_id=ORGANIZATION_ID,
            name="Apollo",
            created_by_user_id=USER_ID,
        )
    )
    session.add(
        ProjectMember(
            project_id=PROJECT_ID,
            user_id=USER_ID,
            role=ProjectMemberRole.ADMIN.value,
        )
    )
    session.add(
        Project(
            id=OTHER_PROJECT_ID,
            organization_id=ORGANIZATION_ID,
            name="Gemini",
            created_by_user_id=USER_ID,
        )
    )
    session.add(
        ConversationSession(
            id=SESSION_ID,
            user_id=USER_ID,
            organization_id=ORGANIZATION_ID,
            project_id=PROJECT_ID,
            title="Project chat",
            status=ConversationSessionStatus.ACTIVE.value,
        )
    )
    await session.commit()
