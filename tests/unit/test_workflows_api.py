"""File guide.

- Use: Contains unit/API tests for workflow list response discipline.
- Usage: Run this file with pytest when checking workflow endpoints.
- Duties: Overrides workflow service and verifies recent-runs payload boundaries.
- Depends on: External packages: fastapi.testclient. Project modules:
  rastin_ai.api.dependencies, services.workflows, and helpers.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from helpers import create_isolated_app

from rastin_ai.services.workflows import WorkflowStatusRecord, WorkflowSummaryRecord

WORKFLOW_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class FakeWorkflowService:
    async def get_workflow_status(self, workflow_id: UUID) -> WorkflowStatusRecord:
        return WorkflowStatusRecord(
            workflow_id=workflow_id,
            session_id=SESSION_ID,
            status="completed",
            result={"answer": "full answer", "workflow_details": []},
            error=None,
            trace_id="trace-test",
            created_at=NOW,
            updated_at=NOW,
            started_at=NOW,
            finished_at=NOW,
        )

    async def list_recent_workflows(self, *, limit: int) -> list[WorkflowSummaryRecord]:
        return [
            WorkflowSummaryRecord(
                workflow_id=WORKFLOW_ID,
                session_id=SESSION_ID,
                status="completed",
                display_label=f"Run limited to {limit}",
                trace_id="trace-test",
                created_at=NOW,
                updated_at=NOW,
                started_at=NOW,
                finished_at=NOW,
            )
        ]


def test_list_workflows_returns_sidebar_metadata_only(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_workflow_status_service] = (
        lambda: FakeWorkflowService()
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/workflows?limit=7")

    assert response.status_code == 200
    assert response.json() == {
        "workflows": [
            {
                "workflow_id": str(WORKFLOW_ID),
                "session_id": str(SESSION_ID),
                "status": "completed",
                "display_label": "Run limited to 7",
                "trace_id": "trace-test",
                "created_at": "2026-08-11T12:00:00Z",
                "updated_at": "2026-08-11T12:00:00Z",
                "started_at": "2026-08-11T12:00:00Z",
                "finished_at": "2026-08-11T12:00:00Z",
            }
        ]
    }
    assert "answer" not in response.text
    assert "workflow_details" not in response.text


def test_get_workflow_can_return_full_result(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_workflow_status_service] = (
        lambda: FakeWorkflowService()
    )

    with TestClient(app) as client:
        response = client.get(f"/api/v1/workflows/{WORKFLOW_ID}")

    assert response.status_code == 200
    assert response.json()["result"] == {
        "answer": "full answer",
        "workflow_details": [],
    }
