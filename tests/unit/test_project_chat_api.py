"""API tests for project-scoped private chat endpoints."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from helpers import create_isolated_app

from rastin_ai.database.enums import OrganizationMemberRole, ProjectMemberRole
from rastin_ai.repositories.conversations import (
    ConversationDocumentReferenceRecord,
    ConversationMessageRecord,
)
from rastin_ai.repositories.organizations import (
    OrganizationMemberRecord,
    OrganizationRecord,
)
from rastin_ai.repositories.projects import ProjectRecord
from rastin_ai.security.auth import AuthenticatedPrincipal
from rastin_ai.services.authorization import ProjectAccessContext
from rastin_ai.services.conversations import (
    ConversationMessageView,
    ConversationSessionSummary,
    ConversationSessionView,
)
from rastin_ai.services.messages import (
    MessageAttachmentInput,
    MessageAttachmentRecord,
)
from rastin_ai.services.project_messages import (
    ProjectMessageSubmission,
    ProjectMessageSubmissionResult,
)
from rastin_ai.services.workflows import WorkflowStatusRecord

ORGANIZATION_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = UUID("22222222-2222-4222-8222-222222222222")
SESSION_ID = UUID("33333333-3333-4333-8333-333333333333")
WORKFLOW_ID = UUID("44444444-4444-4444-8444-444444444444")
USER_MESSAGE_ID = UUID("55555555-5555-4555-8555-555555555555")
ASSISTANT_MESSAGE_ID = UUID("66666666-6666-4666-8666-666666666666")
DOCUMENT_ID = UUID("77777777-7777-4777-8777-777777777777")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


class FakeProjectConversationService:
    def __init__(self) -> None:
        self.created_title: str | None = None

    async def rename_session(
        self, context: ProjectAccessContext, session_id: UUID, *, title: str
    ) -> ConversationSessionSummary:
        assert context.project.id == PROJECT_ID
        assert session_id == SESSION_ID
        return _summary(title=title)

    async def create_session(
        self,
        context: ProjectAccessContext,
        *,
        title: str | None = None,
    ) -> ConversationSessionSummary:
        _ = context
        self.created_title = title
        return _summary(title=title)

    async def list_sessions(
        self,
        context: ProjectAccessContext,
        *,
        limit: int = 50,
    ) -> list[ConversationSessionSummary]:
        _ = context
        _ = limit
        return [_summary()]

    async def get_session(
        self,
        context: ProjectAccessContext,
        session_id: UUID,
    ) -> ConversationSessionView:
        _ = context
        assert session_id == SESSION_ID
        return ConversationSessionView(
            id=SESSION_ID,
            title="Launch",
            status="active",
            created_at=NOW,
            updated_at=NOW,
            messages=(_message_view(USER_MESSAGE_ID, "user", "hello"),),
        )


class FakeProjectMessageService:
    def __init__(self) -> None:
        self.submissions: list[ProjectMessageSubmission] = []

    async def submit(
        self,
        context: ProjectAccessContext,
        submission: ProjectMessageSubmission,
    ) -> ProjectMessageSubmissionResult:
        _ = context
        self.submissions.append(submission)
        return ProjectMessageSubmissionResult(
            workflow_id=WORKFLOW_ID,
            session_id=SESSION_ID,
            user_message=_message_record(USER_MESSAGE_ID, "user", "hello"),
            assistant_message=_message_record(ASSISTANT_MESSAGE_ID, "assistant", "ok"),
            status="answered",
            final_answer="ok",
            attachments=(
                MessageAttachmentRecord(
                    document_id=DOCUMENT_ID,
                    filename="notes.txt",
                    content_type="text/plain",
                    size_bytes=5,
                    status="stored",
                    file_metadata_id=DOCUMENT_ID,
                ),
            ),
            sources=({"document_id": str(DOCUMENT_ID), "filename": "notes.txt"},),
            citations=({"document_id": str(DOCUMENT_ID), "filename": "notes.txt"},),
            workflow_details=(
                {"label": "Build answer context", "status": "completed"},
            ),
        )


class FakeProjectWorkflowService:
    async def get_workflow_status(
        self,
        context: ProjectAccessContext,
        *,
        session_id: UUID,
        workflow_id: UUID,
    ) -> WorkflowStatusRecord:
        _ = context
        assert session_id == SESSION_ID
        assert workflow_id == WORKFLOW_ID
        return WorkflowStatusRecord(
            workflow_id=workflow_id,
            session_id=session_id,
            status="completed",
            result={"status": "answered"},
            error=None,
            trace_id=None,
            created_at=NOW,
            updated_at=NOW,
            started_at=NOW,
            finished_at=NOW,
        )


def test_project_chat_routes_return_safe_typed_contracts(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)
    conversation_service = FakeProjectConversationService()
    message_service = FakeProjectMessageService()

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_project_access_context] = _context
    app.dependency_overrides[dependencies.get_project_conversation_service] = (
        lambda: conversation_service
    )
    app.dependency_overrides[dependencies.get_project_message_submission_service] = (
        lambda: message_service
    )
    app.dependency_overrides[dependencies.get_project_workflow_status_service] = (
        lambda: FakeProjectWorkflowService()
    )

    with TestClient(app) as client:
        create_response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/sessions",
            json={"title": " Launch "},
        )
        list_response = client.get(f"/api/v1/projects/{PROJECT_ID}/sessions")
        detail_response = client.get(
            f"/api/v1/projects/{PROJECT_ID}/sessions/{SESSION_ID}"
        )
        rename_response = client.patch(
            f"/api/v1/projects/{PROJECT_ID}/sessions/{SESSION_ID}",
            json={"title": "Renamed chat"},
        )
        invalid_rename = client.patch(
            f"/api/v1/projects/{PROJECT_ID}/sessions/{SESSION_ID}",
            json={"title": "x" * 256},
        )
        message_response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/sessions/{SESSION_ID}/messages",
            data={"message": "hello"},
            files={"files": ("notes.txt", b"alpha", "text/plain")},
        )
        workflow_response = client.get(
            f"/api/v1/projects/{PROJECT_ID}/sessions/{SESSION_ID}/"
            f"workflows/{WORKFLOW_ID}"
        )

    assert create_response.status_code == 201
    assert create_response.json()["title"] == " Launch "
    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert rename_response.status_code == 200
    assert rename_response.json()["title"] == "Renamed chat"
    assert invalid_rename.status_code == 422
    assert len(detail_response.json()["messages"]) == 1
    assert message_response.status_code == 200
    payload = message_response.json()
    assert payload["workflow_id"] == str(WORKFLOW_ID)
    assert payload["user_message"]["id"] == str(USER_MESSAGE_ID)
    assert payload["assistant_message"]["content"] == "ok"
    assert payload["attachments"][0]["document_id"] == str(DOCUMENT_ID)
    assert "storage_key" not in str(payload)
    assert message_service.submissions == [
        ProjectMessageSubmission(
            message="hello",
            session_id=SESSION_ID,
            attachments=(
                MessageAttachmentInput(
                    filename="notes.txt",
                    content=b"alpha",
                    content_type="text/plain",
                ),
            ),
        )
    ]
    assert workflow_response.status_code == 200
    assert workflow_response.json()["status"] == "completed"


def _context() -> ProjectAccessContext:
    return ProjectAccessContext(
        principal=AuthenticatedPrincipal(
            user_id=USER_ID,
            issuer="test",
            subject=str(USER_ID),
            email="user@example.test",
        ),
        organization=OrganizationRecord(
            id=ORGANIZATION_ID,
            name="Acme",
            slug="acme",
            created_by_user_id=USER_ID,
            created_at=NOW,
            updated_at=NOW,
        ),
        project=ProjectRecord(
            id=PROJECT_ID,
            organization_id=ORGANIZATION_ID,
            name="Apollo",
            description=None,
            created_by_user_id=USER_ID,
            created_at=NOW,
            updated_at=NOW,
        ),
        organization_membership=OrganizationMemberRecord(
            id=UUID("88888888-8888-4888-8888-888888888888"),
            organization_id=ORGANIZATION_ID,
            user_id=USER_ID,
            role=OrganizationMemberRole.MEMBER.value,
            user_is_active=True,
            user_email="user@example.test",
            user_display_name="User",
            created_at=NOW,
            updated_at=NOW,
        ),
        project_membership=None,
        effective_project_role=ProjectMemberRole.MEMBER.value,
    )


def _summary(title: str | None = "Launch") -> ConversationSessionSummary:
    return ConversationSessionSummary(
        id=SESSION_ID,
        title=title,
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )


def _message_view(
    message_id: UUID,
    role: str,
    content: str,
) -> ConversationMessageView:
    record = _message_record(message_id, role, content)
    return ConversationMessageView(
        id=record.id,
        role=record.role,
        sequence=record.sequence,
        content=record.content,
        workflow_id=record.workflow_id,
        status=record.status,
        error_message=record.error_message,
        citations=record.citations,
        sources=record.sources,
        document_references=(
            {
                "document_id": str(DOCUMENT_ID),
                "file_metadata_id": str(DOCUMENT_ID),
                "reference_type": "attachment",
            },
        ),
        created_at=record.created_at,
    )


def _message_record(
    message_id: UUID,
    role: str,
    content: str,
) -> ConversationMessageRecord:
    return ConversationMessageRecord(
        id=message_id,
        session_id=SESSION_ID,
        role=role,
        sequence=1 if role == "user" else 2,
        content=content,
        workflow_id=WORKFLOW_ID if role == "assistant" else None,
        status="answered" if role == "assistant" else "submitted",
        error_message=None,
        citations=(),
        sources=(),
        metadata={},
        document_references=(
            (
                ConversationDocumentReferenceRecord(
                    id=UUID("99999999-9999-4999-8999-999999999999"),
                    message_id=message_id,
                    document_id=DOCUMENT_ID,
                    file_metadata_id=DOCUMENT_ID,
                    reference_type="attachment",
                    created_at=NOW,
                ),
            )
            if role == "user"
            else ()
        ),
        created_at=NOW,
        updated_at=NOW,
    )
