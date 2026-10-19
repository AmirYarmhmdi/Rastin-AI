"""File guide.

- Use: Serves workflow status API endpoints.
- Usage: Included by rastin_ai.api.v1.router.
- Duties: Delegates workflow state lookup to services and returns public schemas.
- Depends on: External packages: fastapi. Project modules:
  rastin_ai.api.dependencies, rastin_ai.schemas.workflows, and
  rastin_ai.services.workflows.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from rastin_ai.api.dependencies import get_workflow_status_service
from rastin_ai.schemas.workflows import WorkflowListResponse, WorkflowStatusResponse
from rastin_ai.services.workflows import WorkflowStatusService

router = APIRouter(prefix="/workflows")


@router.get(
    "",
    response_model=WorkflowListResponse,
    summary="List recent workflow runs",
)
async def list_recent_workflows(
    workflow_service: Annotated[
        WorkflowStatusService,
        Depends(get_workflow_status_service),
    ],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> WorkflowListResponse:
    workflows = await workflow_service.list_recent_workflows(limit=limit)
    return WorkflowListResponse(workflows=workflows)


@router.get(
    "/{workflow_id}",
    response_model=WorkflowStatusResponse,
    summary="Get workflow status",
)
async def get_workflow_status(
    workflow_id: UUID,
    workflow_service: Annotated[
        WorkflowStatusService,
        Depends(get_workflow_status_service),
    ],
) -> WorkflowStatusResponse:
    workflow = await workflow_service.get_workflow_status(workflow_id)
    return WorkflowStatusResponse(
        workflow_id=workflow.workflow_id,
        session_id=workflow.session_id,
        status=workflow.status,
        result=workflow.result,
        error=workflow.error,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        started_at=workflow.started_at,
        finished_at=workflow.finished_at,
    )
