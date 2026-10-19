"""File guide.

- Use: Optional PostgreSQL integration coverage for conversation persistence.
- Usage: Set RASTIN_AI_TEST_DATABASE_URL to a *_test database and run pytest.
- Duties: Verifies real session/message/reference persistence in PostgreSQL.
- Depends on: External packages pytest/sqlalchemy and project database/repositories.
"""

import asyncio
import os
from uuid import UUID

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from rastin_ai.database import Base
from rastin_ai.database.engine import create_database_engine
from rastin_ai.database.enums import (
    ConversationMessageRole,
    ConversationMessageStatus,
)
from rastin_ai.database.models.conversation_session import ConversationSession
from rastin_ai.database.models.document import Document
from rastin_ai.database.models.file_metadata import FileMetadata
from rastin_ai.database.models.user import User
from rastin_ai.database.session import create_session_factory
from rastin_ai.repositories.conversations import (
    ConversationDocumentReferenceCreate,
    ConversationMessageCreate,
    SQLAlchemyConversationRepository,
)

TEST_DATABASE_URL = os.environ.get("RASTIN_AI_TEST_DATABASE_URL")
DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
FILE_METADATA_ID = UUID("12121212-1212-4121-8121-121212121212")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def test_conversation_repository_persists_ordered_messages_and_references() -> None:
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
            session.add(
                User(
                    id=USER_ID,
                    issuer="test",
                    external_subject="conversation-repository",
                    email="conversation-repository@example.test",
                )
            )
            session.add(
                ConversationSession(
                    id=UUID("33333333-3333-4333-8333-333333333333"),
                    user_id=USER_ID,
                    title="Document session",
                    status="active",
                )
            )
            session.add(
                Document(
                    id=DOCUMENT_ID,
                    session_id=UUID("33333333-3333-4333-8333-333333333333"),
                    user_id=USER_ID,
                    name="Referenced document",
                    status="indexed",
                )
            )
            session.add(
                FileMetadata(
                    id=FILE_METADATA_ID,
                    document_id=DOCUMENT_ID,
                    user_id=USER_ID,
                    original_filename="referenced.txt",
                    normalized_extension="txt",
                    content_type="text/plain",
                    storage_key="documents/referenced.txt",
                    storage_backend="local",
                    size_bytes=12,
                    checksum_sha256="0" * 64,
                    status="stored",
                )
            )
            await session.commit()

            repository = SQLAlchemyConversationRepository(session)
            conversation = await repository.create_session(
                user_id=USER_ID,
                title="Persistent chat",
            )
            user_message = await repository.append_message(
                ConversationMessageCreate(
                    session_id=conversation.id,
                    role=ConversationMessageRole.USER,
                    content="Use the referenced document.",
                    document_references=(
                        ConversationDocumentReferenceCreate(
                            document_id=DOCUMENT_ID,
                            file_metadata_id=FILE_METADATA_ID,
                            reference_type="referenced",
                        ),
                    ),
                ),
                user_id=USER_ID,
            )
            assistant_message = await repository.append_message(
                ConversationMessageCreate(
                    session_id=conversation.id,
                    role=ConversationMessageRole.ASSISTANT,
                    content="Grounded answer.",
                    status=ConversationMessageStatus.ANSWERED,
                    citations=({"document_id": str(DOCUMENT_ID)},),
                ),
                user_id=USER_ID,
            )
            loaded = await repository.get_session_with_messages(
                conversation.id,
                user_id=USER_ID,
            )

        assert loaded is not None
        assert [message.sequence for message in loaded.messages] == [1, 2]
        assert loaded.messages[0].id == user_message.id
        assert loaded.messages[1].id == assistant_message.id
        assert loaded.messages[0].document_references[0].document_id == DOCUMENT_ID
        assert loaded.messages[1].citations == ({"document_id": str(DOCUMENT_ID)},)
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()
