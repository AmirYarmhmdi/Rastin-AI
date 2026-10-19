"""File guide.

- Use: Contains unit/API tests for Phase 10 endpoints.
- Usage: Run this file with pytest when checking API integration behavior.
- Duties: Overrides service dependencies and verifies route schemas and errors.
- Depends on: External packages: fastapi.testclient, pytest. Project modules:
  rastin_ai.api.dependencies, rastin_ai.core.exceptions,
  rastin_ai.services, and helpers.
"""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from helpers import create_isolated_app

from rastin_ai.core.exceptions import AppException
from rastin_ai.services.documents import (
    DocumentNotFoundError,
    DocumentRecord,
    DocumentUpload,
    InvalidDocumentUploadError,
)
from rastin_ai.services.questions import QuestionAnswer, QuestionInput
from rastin_ai.services.workflows import WorkflowNotFoundError, WorkflowStatusRecord

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
SECOND_DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
WORKFLOW_ID = UUID("33333333-3333-4333-8333-333333333333")
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
CHECKSUM = hashlib.sha256(b"hello").hexdigest()


class FakeDocumentService:
    def __init__(self) -> None:
        self.uploads: list[DocumentUpload] = []
        self.documents = [
            DocumentRecord(
                document_id=DOCUMENT_ID,
                filename="report.txt",
                content_type="text/plain",
                status="indexed",
                created_at=NOW,
                size_bytes=5,
                normalized_extension=".txt",
                storage_key=f"files/{DOCUMENT_ID}/content.txt",
                storage_backend="local",
                checksum_sha256=CHECKSUM,
                updated_at=NOW,
                file_metadata_id=DOCUMENT_ID,
                file_storage_status="stored",
            )
        ]
        self.fail_upload: AppException | None = None

    async def upload_document(self, upload: DocumentUpload) -> DocumentRecord:
        if self.fail_upload is not None:
            raise self.fail_upload
        self.uploads.append(upload)
        return self.documents[0]

    async def list_documents(self) -> list[DocumentRecord]:
        return self.documents

    async def ensure_documents_exist(self, document_ids: list[UUID]) -> None:
        known_ids = {document.document_id for document in self.documents}
        for document_id in document_ids:
            if document_id not in known_ids:
                raise DocumentNotFoundError(document_id)


class FakeQuestionService:
    def __init__(self) -> None:
        self.requests: list[QuestionInput] = []
        self.failure: AppException | None = None

    async def answer(self, question_input: QuestionInput) -> QuestionAnswer:
        if self.failure is not None:
            raise self.failure
        self.requests.append(question_input)
        return QuestionAnswer(
            answer="The main finding is clear.",
            workflow_id=WORKFLOW_ID,
            sources=(
                {
                    "source_number": 1,
                    "document_id": str(DOCUMENT_ID),
                    "filename": "report.txt",
                    "score": 0.91,
                },
            ),
        )


class FakeWorkflowStatusService:
    def __init__(self) -> None:
        self.failed = False

    async def get_workflow_status(self, workflow_id: UUID) -> WorkflowStatusRecord:
        if workflow_id != WORKFLOW_ID:
            raise WorkflowNotFoundError(workflow_id)
        return WorkflowStatusRecord(
            workflow_id=workflow_id,
            session_id=UUID("55555555-5555-4555-8555-555555555555"),
            status="completed" if not self.failed else "failed",
            result=None if self.failed else {"answer": "done"},
            error="failed safely" if self.failed else None,
            trace_id="trace-test",
            created_at=NOW,
            updated_at=NOW,
            started_at=NOW,
            finished_at=NOW,
        )


@pytest.fixture
def api_client(monkeypatch):
    document_service = FakeDocumentService()
    question_service = FakeQuestionService()
    workflow_service = FakeWorkflowStatusService()
    app = create_isolated_app(monkeypatch)

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_document_service] = (
        lambda: document_service
    )
    app.dependency_overrides[dependencies.get_question_answering_service] = (
        lambda: question_service
    )
    app.dependency_overrides[dependencies.get_workflow_status_service] = (
        lambda: workflow_service
    )

    with TestClient(app) as client:
        yield client, document_service, question_service, workflow_service


def test_upload_document_returns_document_status(api_client) -> None:
    client, document_service, _, _ = api_client

    response = client.post(
        "/api/v1/documents",
        files={"file": ("report.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 201
    assert response.json() == {
        "document_id": str(DOCUMENT_ID),
        "filename": "report.txt",
        "content_type": "text/plain",
        "status": "indexed",
        "workflow_id": None,
        "file_metadata_id": str(DOCUMENT_ID),
        "normalized_extension": ".txt",
        "size_bytes": 5,
        "checksum_sha256": CHECKSUM,
        "file_storage_status": "stored",
        "indexing_error_code": None,
        "indexing_error_message": None,
        "created_at": "2026-08-11T12:00:00Z",
        "updated_at": "2026-08-11T12:00:00Z",
    }
    assert document_service.uploads == [
        DocumentUpload(
            filename="report.txt",
            content=b"hello",
            content_type="text/plain",
        )
    ]


def test_upload_document_rejects_missing_file(api_client) -> None:
    client, _, _, _ = api_client

    response = client.post("/api/v1/documents")

    assert response.status_code == 422


def test_upload_document_returns_service_error(api_client) -> None:
    client, document_service, _, _ = api_client
    document_service.fail_upload = InvalidDocumentUploadError("bad upload")

    response = client.post(
        "/api/v1/documents",
        files={"file": ("bad.txt", b"bad", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_DOCUMENT_UPLOAD"


def test_list_documents_returns_known_documents(api_client) -> None:
    client, _, _, _ = api_client

    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    assert response.json() == {
        "documents": [
            {
                "id": str(DOCUMENT_ID),
                "filename": "report.txt",
                "content_type": "text/plain",
                "status": "indexed",
                "created_at": "2026-08-11T12:00:00Z",
                "file_metadata_id": str(DOCUMENT_ID),
                "normalized_extension": ".txt",
                "size_bytes": 5,
                "checksum_sha256": CHECKSUM,
                "file_storage_status": "stored",
                "indexing_error_code": None,
                "indexing_error_message": None,
                "updated_at": "2026-08-11T12:00:00Z",
            }
        ]
    }


def test_ask_question_returns_answer_sources_and_workflow(api_client) -> None:
    client, _, question_service, _ = api_client

    response = client.post(
        "/api/v1/questions",
        json={"question": "What changed?", "document_ids": [str(DOCUMENT_ID)]},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "The main finding is clear."
    assert response.json()["workflow_id"] == str(WORKFLOW_ID)
    assert response.json()["sources"][0]["filename"] == "report.txt"
    assert question_service.requests == [
        QuestionInput(question="What changed?", document_ids=[DOCUMENT_ID])
    ]


def test_ask_question_rejects_empty_question(api_client) -> None:
    client, _, _, _ = api_client

    response = client.post("/api/v1/questions", json={"question": "   "})

    assert response.status_code == 422


def test_ask_question_returns_missing_document_error(api_client) -> None:
    client, _, question_service, _ = api_client
    question_service.failure = DocumentNotFoundError(SECOND_DOCUMENT_ID)

    response = client.post(
        "/api/v1/questions",
        json={"question": "What changed?", "document_ids": [str(SECOND_DOCUMENT_ID)]},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_ask_question_returns_workflow_failure(api_client) -> None:
    client, _, question_service, _ = api_client
    question_service.failure = AppException(
        "Question answering failed.",
        status_code=502,
        error_code="QUESTION_ANSWERING_FAILED",
    )

    response = client.post("/api/v1/questions", json={"question": "What changed?"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "QUESTION_ANSWERING_FAILED"


def test_get_workflow_status_returns_completed_state(api_client) -> None:
    client, _, _, _ = api_client

    response = client.get(f"/api/v1/workflows/{WORKFLOW_ID}")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["session_id"] == "55555555-5555-4555-8555-555555555555"
    assert response.json()["result"] == {"answer": "done"}
    assert response.json()["error"] is None


def test_get_workflow_status_returns_failed_state(api_client) -> None:
    client, _, _, workflow_service = api_client
    workflow_service.failed = True

    response = client.get(f"/api/v1/workflows/{WORKFLOW_ID}")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["result"] is None
    assert response.json()["error"] == "failed safely"


def test_get_workflow_status_returns_not_found(api_client) -> None:
    client, _, _, _ = api_client
    unknown_workflow_id = UUID("44444444-4444-4444-8444-444444444444")

    response = client.get(f"/api/v1/workflows/{unknown_workflow_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKFLOW_NOT_FOUND"


def test_phase10_endpoints_are_in_openapi(api_client) -> None:
    client, _, _, _ = api_client

    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/documents" in paths
    assert "/api/v1/messages" in paths
    assert "/api/v1/questions" in paths
    assert "/api/v1/sessions" in paths
    assert "/api/v1/sessions/{session_id}" in paths
    assert "/api/v1/workflows" in paths
    assert "/api/v1/workflows/{workflow_id}" in paths
