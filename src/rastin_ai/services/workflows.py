"""File guide.

- Use: Reads public workflow execution status through repository abstractions.
- Usage: Import WorkflowStatusService from rastin_ai.services.workflows.
- Duties: Defines workflow status API service and not-found errors.
- Depends on: Project modules: rastin_ai.core.exceptions and
  rastin_ai.repositories.workflow_execution.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from fastapi import status

from rastin_ai.core.exceptions import AppException
from rastin_ai.repositories.workflow_execution import (
    WorkflowExecutionRecord,
    WorkflowExecutionRepository,
)


class WorkflowNotFoundError(AppException):
    """Raised when a workflow execution ID is not known."""

    def __init__(self, workflow_id: UUID) -> None:
        super().__init__(
            "Workflow not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="WORKFLOW_NOT_FOUND",
            details={"workflow_id": str(workflow_id)},
        )


@dataclass(frozen=True)
class WorkflowStatusRecord:
    workflow_id: UUID
    session_id: UUID
    status: str
    result: dict[str, Any] | None
    error: str | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True)
class WorkflowSummaryRecord:
    workflow_id: UUID
    session_id: UUID
    status: str
    display_label: str
    trace_id: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class WorkflowStatusService(Protocol):
    async def get_workflow_status(self, workflow_id: UUID) -> WorkflowStatusRecord:
        """Return public workflow status for a workflow execution."""

    async def list_recent_workflows(self, *, limit: int) -> list[WorkflowSummaryRecord]:
        """Return UI-safe recent workflow summaries."""


class RepositoryWorkflowStatusService:
    """Workflow status service backed by workflow execution persistence."""

    def __init__(
        self, repository: WorkflowExecutionRepository, *, user_id: UUID
    ) -> None:
        self._repository = repository
        self._user_id = user_id

    async def get_workflow_status(self, workflow_id: UUID) -> WorkflowStatusRecord:
        record = await self._repository.get_by_id(
            workflow_id,
            user_id=self._user_id,
        )
        if record is None:
            raise WorkflowNotFoundError(workflow_id)

        return _workflow_status_from_record(record)

    async def list_recent_workflows(self, *, limit: int) -> list[WorkflowSummaryRecord]:
        records = await self._repository.list_recent(
            user_id=self._user_id,
            limit=limit,
        )
        return [_workflow_summary_from_record(record) for record in records]


def _workflow_status_from_record(
    record: WorkflowExecutionRecord,
) -> WorkflowStatusRecord:
    return WorkflowStatusRecord(
        workflow_id=record.id,
        session_id=record.session_id,
        status=record.status,
        result=record.output_payload,
        error=record.error_message,
        trace_id=record.trace_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def _workflow_summary_from_record(
    record: WorkflowExecutionRecord,
) -> WorkflowSummaryRecord:
    return WorkflowSummaryRecord(
        workflow_id=record.id,
        session_id=record.session_id,
        status=record.status,
        display_label=_display_label(record),
        trace_id=record.trace_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def _display_label(record: WorkflowExecutionRecord) -> str:
    question = (record.input_payload or {}).get("question")
    if isinstance(question, str) and question.strip():
        return _compact_label(question)

    return _compact_label(record.workflow_name.replace("_", " "))


def _compact_label(value: str, *, max_length: int = 80) -> str:
    compacted = " ".join(value.split())
    if len(compacted) <= max_length:
        return compacted

    return f"{compacted[: max_length - 1].rstrip()}..."
