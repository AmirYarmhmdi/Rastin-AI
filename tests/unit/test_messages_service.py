"""File guide.

- Use: Contains unit tests for UI message submission service behavior.
- Usage: Run this file with pytest when checking message submission.
- Duties: Uses fakes to verify persisted sessions, turns, references, and history.
- Depends on: Project modules: repositories.conversations and services.
"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

import rastin_ai.observability.langfuse as langfuse_observability
from rastin_ai.core.exceptions import AppException
from rastin_ai.database.enums import (
    ConversationMessageStatus,
)
from rastin_ai.repositories.conversations import (
    ConversationDocumentReferenceCreate,
    ConversationDocumentReferenceRecord,
    ConversationMessageCreate,
    ConversationMessageRecord,
    ConversationRepository,
    ConversationSessionRecord,
)
from rastin_ai.services.conversations import (
    ConversationHistoryBuilder,
    ConversationHistoryItem,
    ConversationSessionNotFoundError,
)
from rastin_ai.services.documents import DocumentRecord, DocumentUpload
from rastin_ai.services.messages import (
    MessageAttachmentInput,
    MessageSubmission,
    MessageSubmissionService,
)
from rastin_ai.services.questions import QuestionAnswer, QuestionInput

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
FILE_METADATA_ID = UUID("12121212-1212-4121-8121-121212121212")
REFERENCED_DOCUMENT_ID = UUID("13131313-1313-4131-8131-131313131313")
REFERENCED_FILE_METADATA_ID = UUID("14141414-1414-4141-8141-141414141414")
WORKFLOW_ID = UUID("22222222-2222-4222-8222-222222222222")
SESSION_ID = UUID("33333333-3333-4333-8333-333333333333")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class FakeDocumentService:
    def __init__(self) -> None:
        self.uploads: list[DocumentUpload] = []

    async def upload_document(self, upload: DocumentUpload) -> DocumentRecord:
        self.uploads.append(upload)
        return DocumentRecord(
            document_id=DOCUMENT_ID,
            filename=upload.filename,
            content_type=upload.content_type,
            status="indexed",
            created_at=NOW,
            size_bytes=len(upload.content),
            file_metadata_id=FILE_METADATA_ID,
            file_storage_status="stored",
        )

    async def list_documents(self) -> list[DocumentRecord]:
        return []

    async def ensure_documents_exist(self, document_ids: list[UUID]) -> None:
        _ = document_ids

    async def get_documents(self, document_ids: list[UUID]) -> list[DocumentRecord]:
        records = []
        for document_id in document_ids:
            records.append(
                DocumentRecord(
                    document_id=document_id,
                    filename="referenced.txt",
                    content_type="text/plain",
                    status="indexed",
                    created_at=NOW,
                    size_bytes=10,
                    file_metadata_id=REFERENCED_FILE_METADATA_ID,
                    file_storage_status="stored",
                )
            )
        return records


class FakeQuestionService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[QuestionInput] = []

    async def answer(self, question_input: QuestionInput) -> QuestionAnswer:
        self.requests.append(question_input)
        if self.fail:
            raise AppException("Question answering failed safely.")
        return QuestionAnswer(
            answer="Answer from indexed context.",
            workflow_id=WORKFLOW_ID,
            session_id=question_input.session_id,
            sources=({"filename": "indexed.txt", "score": 0.9},),
            citations=(
                {
                    "document_id": str(
                        question_input.document_ids[0]
                        if question_input.document_ids
                        else DOCUMENT_ID
                    ),
                    "source_location": {"line_start": 1, "line_end": 1},
                },
            ),
            workflow_details=(
                {
                    "label": "Retrieve indexed context",
                    "status": "completed",
                    "summary": "1 indexed source(s) returned.",
                },
            ),
        )


class FakeConversationRepository(ConversationRepository):
    def __init__(self) -> None:
        self.sessions: dict[UUID, ConversationSessionRecord] = {}
        self.messages: dict[UUID, list[ConversationMessageRecord]] = {}
        self.appended: list[ConversationMessageRecord] = []
        self.workflow_updates: list[tuple[UUID, UUID | None]] = []

    async def create_session(
        self,
        *,
        user_id: UUID,
        title: str | None = None,
    ) -> ConversationSessionRecord:
        assert user_id == USER_ID
        session = ConversationSessionRecord(
            user_id=user_id,
            id=uuid4(),
            title=title,
            status="active",
            created_at=NOW,
            updated_at=NOW,
        )
        self.sessions[session.id] = session
        self.messages[session.id] = []
        return session

    async def get_session(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
    ) -> ConversationSessionRecord | None:
        assert user_id == USER_ID
        return self.sessions.get(session_id)

    async def get_session_with_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
    ) -> ConversationSessionRecord | None:
        assert user_id == USER_ID
        session = self.sessions.get(session_id)
        if session is None:
            return None
        return replace(session, messages=tuple(self.messages[session_id]))

    async def list_sessions(
        self,
        *,
        user_id: UUID,
        limit: int,
    ) -> list[ConversationSessionRecord]:
        assert user_id == USER_ID
        return list(self.sessions.values())[:limit]

    async def append_message(
        self,
        message: ConversationMessageCreate,
        *,
        user_id: UUID,
    ) -> ConversationMessageRecord:
        assert user_id == USER_ID
        message_id = uuid4()
        sequence = len(self.messages.setdefault(message.session_id, [])) + 1
        record = ConversationMessageRecord(
            id=message_id,
            session_id=message.session_id,
            role=message.role.value,
            sequence=sequence,
            content=message.content,
            workflow_id=message.workflow_id,
            status=message.status.value,
            error_message=message.error_message,
            citations=message.citations,
            sources=message.sources,
            metadata=message.metadata or {},
            document_references=(
                tuple(
                    _reference_record(reference, message_id)
                    for reference in message.document_references
                )
                if message.document_references
                else ()
            ),
            created_at=NOW,
            updated_at=NOW,
        )
        self.messages[message.session_id].append(record)
        self.appended.append(record)
        return record

    async def update_message_workflow(
        self,
        message_id: UUID,
        workflow_id: UUID | None,
        *,
        user_id: UUID,
    ) -> ConversationMessageRecord:
        assert user_id == USER_ID
        self.workflow_updates.append((message_id, workflow_id))
        for session_messages in self.messages.values():
            for index, message in enumerate(session_messages):
                if message.id == message_id:
                    updated = replace(message, workflow_id=workflow_id)
                    session_messages[index] = updated
                    self.appended = [
                        updated if item.id == message_id else item
                        for item in self.appended
                    ]
                    return updated
        raise KeyError(str(message_id))

    async def recent_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
        limit: int,
    ) -> list[ConversationMessageRecord]:
        assert user_id == USER_ID
        return self.messages.get(session_id, [])[-limit:]


def _reference_record(
    reference: ConversationDocumentReferenceCreate,
    message_id: UUID,
) -> ConversationDocumentReferenceRecord:
    return ConversationDocumentReferenceRecord(
        id=uuid4(),
        message_id=message_id,
        document_id=reference.document_id,
        file_metadata_id=reference.file_metadata_id,
        reference_type=reference.reference_type,
        created_at=NOW,
    )


def _service(
    *,
    repository: FakeConversationRepository | None = None,
    question_service: FakeQuestionService | None = None,
) -> tuple[
    MessageSubmissionService,
    FakeDocumentService,
    FakeQuestionService,
    FakeConversationRepository,
]:
    document_service = FakeDocumentService()
    question_service = question_service or FakeQuestionService()
    repository = repository or FakeConversationRepository()
    return (
        MessageSubmissionService(
            document_service=document_service,
            question_service=question_service,
            conversation_repository=repository,
            history_builder=ConversationHistoryBuilder(
                repository,
                user_id=USER_ID,
                max_turns=2,
                max_chars=200,
            ),
            user_id=USER_ID,
        ),
        document_service,
        question_service,
        repository,
    )


def test_first_message_creates_session_and_two_ordered_turns() -> None:
    asyncio.run(_run_first_message_test())


def test_message_submission_records_workflow_spans(monkeypatch) -> None:
    from test_observability import FakeLangfuseClient

    fake_client = FakeLangfuseClient()
    monkeypatch.setattr(
        langfuse_observability,
        "_get_langfuse_client",
        lambda settings=None: fake_client,
    )

    asyncio.run(_run_first_message_test())

    names = [
        observation.start_kwargs["name"] for observation in fake_client.observations
    ]
    assert "message.workflow" in names
    assert "message.session.resolve" in names
    assert "message.history.load" in names
    assert "message.attachments.store" in names
    assert "message.attachments.extract" in names
    assert "message.persist.user" in names
    assert "message.question_answer" in names
    assert "message.persist.workflow_link" in names
    assert "message.persist.assistant" in names


async def _run_first_message_test() -> None:
    service, document_service, question_service, repository = _service()

    result = await service.submit(
        MessageSubmission(
            message="What changed?",
            attachments=(
                MessageAttachmentInput(
                    filename="report.txt",
                    content=b"hello",
                    content_type="text/plain",
                ),
            ),
        )
    )

    assert document_service.uploads == [
        DocumentUpload(
            filename="report.txt",
            content=b"hello",
            content_type="text/plain",
        )
    ]
    assert len(repository.sessions) == 1
    assert result.session_id in repository.sessions
    assert [message.role for message in repository.appended] == ["user", "assistant"]
    assert [message.sequence for message in repository.appended] == [1, 2]
    assert repository.appended[0].document_references[0].document_id == DOCUMENT_ID
    assert repository.appended[0].document_references[0].file_metadata_id == (
        FILE_METADATA_ID
    )
    assert repository.appended[0].document_references[0].reference_type == "attachment"
    assert question_service.requests[0].session_id == result.session_id
    assert question_service.requests[0].conversation_history == ()
    assert question_service.requests[0].attachments[0].filename == "report.txt"
    assert question_service.requests[0].attachments[0].text == "hello"
    assert result.workflow_id == WORKFLOW_ID
    assert result.user_message_id == repository.appended[0].id
    assert result.assistant_message_id == repository.appended[1].id
    assert result.citations == repository.appended[1].citations
    assert result.artifacts == ()


def test_followup_reuses_session_and_loads_bounded_history() -> None:
    asyncio.run(_run_followup_test())


async def _run_followup_test() -> None:
    repository = FakeConversationRepository()
    service, _, question_service, repository = _service(repository=repository)
    first = await service.submit(MessageSubmission(message="First question"))

    second = await service.submit(
        MessageSubmission(
            message="Follow up",
            session_id=first.session_id,
            document_ids=(REFERENCED_DOCUMENT_ID,),
        )
    )

    assert second.session_id == first.session_id
    assert len(repository.sessions) == 1
    assert [message.sequence for message in repository.messages[first.session_id]] == [
        1,
        2,
        3,
        4,
    ]
    assert question_service.requests[1].conversation_history == (
        ConversationHistoryItem(role="user", content="First question"),
        ConversationHistoryItem(
            role="assistant", content="Answer from indexed context."
        ),
    )
    assert question_service.requests[1].document_ids == [REFERENCED_DOCUMENT_ID]
    user_turn = repository.messages[first.session_id][2]
    assert user_turn.document_references[0].document_id == REFERENCED_DOCUMENT_ID
    assert user_turn.document_references[0].reference_type == "referenced"
    assert repository.workflow_updates == [
        (repository.messages[first.session_id][0].id, WORKFLOW_ID),
        (repository.messages[first.session_id][2].id, WORKFLOW_ID),
    ]


def test_nonexistent_session_id_is_rejected() -> None:
    asyncio.run(_run_missing_session_test())


async def _run_missing_session_test() -> None:
    service, _, _, repository = _service()

    with pytest.raises(ConversationSessionNotFoundError):
        await service.submit(MessageSubmission(message="Hello", session_id=SESSION_ID))

    assert repository.appended == []


def test_processing_failure_preserves_user_message_and_assistant_error_turn() -> None:
    asyncio.run(_run_processing_failure_test())


async def _run_processing_failure_test() -> None:
    service, _, _, repository = _service(
        question_service=FakeQuestionService(fail=True),
    )

    with pytest.raises(AppException):
        await service.submit(MessageSubmission(message="Break safely"))

    assert len(repository.sessions) == 1
    assert [message.role for message in repository.appended] == ["user", "assistant"]
    assert repository.appended[0].content == "Break safely"
    assert repository.appended[1].status == ConversationMessageStatus.FAILED.value
    assert repository.appended[1].error_message == "Question answering failed safely."
    assert repository.workflow_updates == []


def test_new_sessions_do_not_share_histories() -> None:
    asyncio.run(_run_isolated_history_test())


async def _run_isolated_history_test() -> None:
    service, _, question_service, _ = _service()
    await service.submit(MessageSubmission(message="Session one"))
    await service.submit(MessageSubmission(message="Session two"))

    assert question_service.requests[0].conversation_history == ()
    assert question_service.requests[1].conversation_history == ()
