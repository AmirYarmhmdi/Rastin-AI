"""File guide.

- Use: Contains API tests for read-only conversation session endpoints.
- Usage: Run with pytest when checking conversation session API behavior.
- Duties: Overrides conversation service and verifies response shape/errors.
- Depends on: External package fastapi.testclient and project helpers/services.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from helpers import create_isolated_app

from rastin_ai.services.conversations import (
    ConversationMessageView,
    ConversationSessionNotFoundError,
    ConversationSessionSummary,
    ConversationSessionView,
)

SESSION_ID = UUID("33333333-3333-4333-8333-333333333333")
MESSAGE_ID = UUID("44444444-4444-4444-8444-444444444444")
WORKFLOW_ID = UUID("22222222-2222-4222-8222-222222222222")
DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
FILE_METADATA_ID = UUID("12121212-1212-4121-8121-121212121212")
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class FakeConversationService:
    async def list_sessions(
        self,
        *,
        limit: int = 50,
    ) -> list[ConversationSessionSummary]:
        _ = limit
        return [
            ConversationSessionSummary(
                id=SESSION_ID,
                title="Question about plans",
                status="active",
                created_at=NOW,
                updated_at=NOW,
            )
        ]

    async def get_session(self, session_id: UUID) -> ConversationSessionView:
        if session_id != SESSION_ID:
            raise ConversationSessionNotFoundError(session_id)
        return ConversationSessionView(
            id=SESSION_ID,
            title="Question about plans",
            status="active",
            created_at=NOW,
            updated_at=NOW,
            messages=(
                ConversationMessageView(
                    id=MESSAGE_ID,
                    role="assistant",
                    sequence=2,
                    content="The plan changed.",
                    workflow_id=WORKFLOW_ID,
                    status="answered",
                    error_message=None,
                    citations=({"document_id": str(DOCUMENT_ID)},),
                    sources=({"document_id": str(DOCUMENT_ID), "score": 0.9},),
                    document_references=(
                        {
                            "document_id": str(DOCUMENT_ID),
                            "file_metadata_id": str(FILE_METADATA_ID),
                            "reference_type": "referenced",
                        },
                    ),
                    created_at=NOW,
                ),
            ),
        )


def test_list_sessions_returns_recent_sessions(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_conversation_service] = (
        lambda: FakeConversationService()
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/sessions?limit=10")

    assert response.status_code == 200
    assert response.json() == {
        "sessions": [
            {
                "id": str(SESSION_ID),
                "title": "Question about plans",
                "status": "active",
                "created_at": "2026-08-11T12:00:00Z",
                "updated_at": "2026-08-11T12:00:00Z",
            }
        ]
    }


def test_get_session_returns_ordered_messages(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_conversation_service] = (
        lambda: FakeConversationService()
    )

    with TestClient(app) as client:
        response = client.get(f"/api/v1/sessions/{SESSION_ID}")

    assert response.status_code == 200
    assert response.json()["messages"] == [
        {
            "id": str(MESSAGE_ID),
            "role": "assistant",
            "sequence": 2,
            "content": "The plan changed.",
            "workflow_id": str(WORKFLOW_ID),
            "status": "answered",
            "error_message": None,
            "citations": [{"document_id": str(DOCUMENT_ID)}],
            "sources": [{"document_id": str(DOCUMENT_ID), "score": 0.9}],
            "document_references": [
                {
                    "document_id": str(DOCUMENT_ID),
                    "file_metadata_id": str(FILE_METADATA_ID),
                    "reference_type": "referenced",
                }
            ],
            "created_at": "2026-08-11T12:00:00Z",
        }
    ]


def test_get_session_rejects_unknown_session(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_conversation_service] = (
        lambda: FakeConversationService()
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/sessions/99999999-9999-4999-8999-999999999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_SESSION_NOT_FOUND"
