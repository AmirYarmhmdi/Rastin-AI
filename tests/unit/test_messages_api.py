"""File guide.

- Use: Contains unit/API tests for the UI message endpoint.
- Usage: Run this file with pytest when checking message API behavior.
- Duties: Overrides services and verifies multipart request/response shape.
- Depends on: External packages: fastapi.testclient. Project modules:
  rastin_ai.api.dependencies, services.messages, and helpers.
"""

from uuid import UUID

from fastapi.testclient import TestClient
from helpers import create_isolated_app

from rastin_ai.core.config import Settings
from rastin_ai.security.auth import AuthenticatedPrincipal
from rastin_ai.services.documents import DocumentRecord, DocumentUpload
from rastin_ai.services.messages import (
    MessageAttachmentInput,
    MessageAttachmentRecord,
    MessageSubmission,
    MessageSubmissionResult,
)

WORKFLOW_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
DOCUMENT_ID = UUID("33333333-3333-4333-8333-333333333333")
USER_MESSAGE_ID = UUID("44444444-4444-4444-8444-444444444444")
ASSISTANT_MESSAGE_ID = UUID("55555555-5555-4555-8555-555555555555")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


class FakeMessageSubmissionService:
    def __init__(self) -> None:
        self.submissions: list[MessageSubmission] = []

    async def submit(
        self,
        submission: MessageSubmission,
    ) -> MessageSubmissionResult:
        self.submissions.append(submission)
        return MessageSubmissionResult(
            workflow_id=WORKFLOW_ID,
            session_id=SESSION_ID,
            user_message_id=USER_MESSAGE_ID,
            assistant_message_id=ASSISTANT_MESSAGE_ID,
            status="completed",
            final_answer="The indexed evidence points to growth.",
            attachments=(
                MessageAttachmentRecord(
                    document_id=DOCUMENT_ID,
                    filename="report.txt",
                    content_type="text/plain",
                    size_bytes=5,
                    status="stored",
                ),
            ),
            sources=({"filename": "indexed.txt", "score": 0.91},),
            citations=(
                {
                    "document_id": str(DOCUMENT_ID),
                    "source_location": {"line_start": 1, "line_end": 2},
                },
            ),
            artifacts=(),
            workflow_details=(
                {
                    "label": "Store attachments",
                    "status": "completed",
                    "summary": (
                        "1 file(s) stored. 1 uploaded file(s) used as direct "
                        "answer context."
                    ),
                },
            ),
        )


class FakeDocumentService:
    async def upload_document(self, upload: DocumentUpload) -> DocumentRecord:
        raise AssertionError("Document upload should not run when Qdrant is missing.")

    async def list_documents(self) -> list[DocumentRecord]:
        return []

    async def ensure_documents_exist(self, document_ids: list[UUID]) -> None:
        _ = document_ids


class FakeWorkflowExecutionRepository:
    pass


def test_submit_message_accepts_text_and_files(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)
    service = FakeMessageSubmissionService()

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_message_submission_service] = (
        lambda: service
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/messages",
            data={"message": "What changed?"},
            files={"files": ("report.txt", b"hello", "text/plain")},
        )

    assert response.status_code == 200
    assert response.json() == {
        "workflow_id": str(WORKFLOW_ID),
        "session_id": str(SESSION_ID),
        "user_message_id": str(USER_MESSAGE_ID),
        "assistant_message_id": str(ASSISTANT_MESSAGE_ID),
        "status": "completed",
        "final_answer": "The indexed evidence points to growth.",
        "attachments": [
            {
                "document_id": str(DOCUMENT_ID),
                "filename": "report.txt",
                "content_type": "text/plain",
                "size_bytes": 5,
                "status": "stored",
            }
        ],
        "sources": [{"filename": "indexed.txt", "score": 0.91}],
        "citations": [
            {
                "document_id": str(DOCUMENT_ID),
                "source_location": {"line_start": 1, "line_end": 2},
            }
        ],
        "artifacts": [],
        "workflow_details": [
            {
                "label": "Store attachments",
                "status": "completed",
                "summary": (
                    "1 file(s) stored. 1 uploaded file(s) used as direct "
                    "answer context."
                ),
            }
        ],
    }
    assert service.submissions == [
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
    ]


def test_submit_message_accepts_session_and_document_scope(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)
    service = FakeMessageSubmissionService()

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_message_submission_service] = (
        lambda: service
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/messages",
            data={
                "message": "Continue from that document",
                "session_id": str(SESSION_ID),
                "document_ids": str(DOCUMENT_ID),
            },
        )

    assert response.status_code == 200
    assert service.submissions == [
        MessageSubmission(
            message="Continue from that document",
            session_id=SESSION_ID,
            document_ids=(DOCUMENT_ID,),
        )
    ]


def test_submit_message_rejects_empty_message(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)
    service = FakeMessageSubmissionService()

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_message_submission_service] = (
        lambda: service
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/messages", data={"message": " "})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_MESSAGE"
    assert service.submissions == []


def test_submit_message_returns_service_unavailable_when_qdrant_is_not_configured(
    monkeypatch,
) -> None:
    app = create_isolated_app(monkeypatch)

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_settings] = lambda: Settings(
        OPENAI_API_KEY="test-openai-key",
        QDRANT_URL=None,
    )
    app.dependency_overrides[dependencies.get_document_service] = (
        lambda: FakeDocumentService()
    )
    app.dependency_overrides[dependencies.get_workflow_execution_repository] = (
        lambda: FakeWorkflowExecutionRepository()
    )
    app.dependency_overrides[dependencies.get_current_principal] = lambda: (
        AuthenticatedPrincipal(
            user_id=USER_ID,
            issuer="test",
            subject="messages-api",
        )
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/messages",
            data={"message": "What changed?"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "QUESTION_ANSWERING_UNAVAILABLE",
            "message": (
                "Question-answering service is unavailable because Qdrant is not "
                "configured. Set QDRANT_URL before retrying."
            ),
            "details": None,
        }
    }
    assert "Traceback" not in response.text
    assert "VectorStoreError" not in response.text
