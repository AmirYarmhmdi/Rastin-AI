"""File guide.

- Use: Contains unit tests for conversation read APIs and history construction.
- Usage: Run with pytest when checking persisted conversation behavior.
- Duties: Verifies bounded history and read-only session views through fakes.
- Depends on: Project modules: repositories.conversations and services.conversations.
"""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from rastin_ai.repositories.conversations import (
    ConversationMessageRecord,
    ConversationSessionRecord,
)
from rastin_ai.services.conversations import (
    ConversationHistoryBuilder,
    ConversationHistoryItem,
    ConversationSessionNotFoundError,
    RepositoryConversationService,
)

SESSION_ID = UUID("33333333-3333-4333-8333-333333333333")
WORKFLOW_ID = UUID("22222222-2222-4222-8222-222222222222")
DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class FakeConversationRepository:
    def __init__(self) -> None:
        self.session = ConversationSessionRecord(
            user_id=USER_ID,
            id=SESSION_ID,
            title="Conversation",
            status="active",
            created_at=NOW,
            updated_at=NOW,
            messages=(
                _message(1, "user", "First question"),
                _message(
                    2,
                    "assistant",
                    "First answer",
                    workflow_id=WORKFLOW_ID,
                    citations=({"document_id": str(DOCUMENT_ID)},),
                ),
                _message(3, "user", "Second question"),
            ),
        )
        self.recent_limit: int | None = None

    async def list_sessions(
        self,
        *,
        user_id: UUID,
        limit: int,
    ) -> list[ConversationSessionRecord]:
        assert user_id == USER_ID
        return [self.session][:limit]

    async def get_session_with_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
    ) -> ConversationSessionRecord | None:
        assert user_id == USER_ID
        if session_id != SESSION_ID:
            return None
        return self.session

    async def recent_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
        limit: int,
    ) -> list[ConversationMessageRecord]:
        assert session_id == SESSION_ID
        assert user_id == USER_ID
        self.recent_limit = limit
        return list(self.session.messages[-limit:])


def _message(
    sequence: int,
    role: str,
    content: str,
    *,
    workflow_id: UUID | None = None,
    citations: tuple[dict, ...] = (),
) -> ConversationMessageRecord:
    return ConversationMessageRecord(
        id=UUID(f"00000000-0000-4000-8000-{sequence:012d}"),
        session_id=SESSION_ID,
        role=role,
        sequence=sequence,
        content=content,
        workflow_id=workflow_id,
        status="answered" if role == "assistant" else "submitted",
        error_message=None,
        citations=citations,
        sources=(),
        metadata={},
        document_references=(),
        created_at=NOW,
        updated_at=NOW,
    )


def test_conversation_service_lists_and_fetches_ordered_messages() -> None:
    asyncio.run(_run_read_service_test())


async def _run_read_service_test() -> None:
    repository = FakeConversationRepository()
    service = RepositoryConversationService(repository, user_id=USER_ID)

    sessions = await service.list_sessions(limit=50)
    session = await service.get_session(SESSION_ID)

    assert sessions[0].id == SESSION_ID
    assert [message.sequence for message in session.messages] == [1, 2, 3]
    assert session.messages[1].workflow_id == WORKFLOW_ID
    assert session.messages[1].citations == ({"document_id": str(DOCUMENT_ID)},)


def test_conversation_service_rejects_unknown_session() -> None:
    asyncio.run(_run_missing_session_test())


async def _run_missing_session_test() -> None:
    service = RepositoryConversationService(
        FakeConversationRepository(), user_id=USER_ID
    )

    with pytest.raises(ConversationSessionNotFoundError):
        await service.get_session(UUID("99999999-9999-4999-8999-999999999999"))


def test_history_builder_bounds_turns_and_characters() -> None:
    asyncio.run(_run_history_builder_test())


async def _run_history_builder_test() -> None:
    repository = FakeConversationRepository()
    builder = ConversationHistoryBuilder(
        repository,
        user_id=USER_ID,
        max_turns=1,
        max_chars=22,
    )

    history = await builder.build(SESSION_ID)

    assert repository.recent_limit == 2
    assert history == (ConversationHistoryItem(role="user", content="Second question"),)


def test_history_builder_can_be_disabled() -> None:
    asyncio.run(_run_disabled_history_test())


async def _run_disabled_history_test() -> None:
    repository = FakeConversationRepository()
    builder = ConversationHistoryBuilder(
        repository,
        user_id=USER_ID,
        max_turns=0,
        max_chars=100,
    )

    assert await builder.build(SESSION_ID) == ()
    assert repository.recent_limit is None
