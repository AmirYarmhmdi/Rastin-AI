"""Project-scoped workflow status services."""

from uuid import UUID

from rastin_ai.repositories.workflow_execution import WorkflowExecutionRepository
from rastin_ai.services.authorization import (
    PROJECT_PERMISSION_CHATS_CREATE,
    AuthorizationService,
    ProjectAccessContext,
)
from rastin_ai.services.workflows import (
    WorkflowNotFoundError,
    WorkflowStatusRecord,
    _workflow_status_from_record,
)


class ProjectWorkflowStatusService:
    """Read project chat workflow state through private session ownership."""

    def __init__(
        self,
        repository: WorkflowExecutionRepository,
        *,
        authorization_service: AuthorizationService,
    ) -> None:
        self._repository = repository
        self._authorization_service = authorization_service

    async def get_workflow_status(
        self,
        context: ProjectAccessContext,
        *,
        session_id: UUID,
        workflow_id: UUID,
    ) -> WorkflowStatusRecord:
        self._authorization_service.require_project_permission(
            context,
            PROJECT_PERMISSION_CHATS_CREATE,
        )
        record = await self._repository.get_project_workflow(
            workflow_id,
            user_id=context.principal.user_id,
            organization_id=context.organization.id,
            project_id=context.project.id,
            session_id=session_id,
        )
        if record is None:
            raise WorkflowNotFoundError(workflow_id)
        return _workflow_status_from_record(record)
