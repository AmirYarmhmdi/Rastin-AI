"""Project metadata and membership endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from rastin_ai.api.dependencies import (
    get_project_access_context,
    get_project_service,
)
from rastin_ai.schemas.projects import (
    ProjectMemberCreateRequest,
    ProjectMemberListResponse,
    ProjectMemberResponse,
    ProjectResponse,
)
from rastin_ai.services.authorization import ProjectAccessContext
from rastin_ai.services.projects import (
    ProjectMemberInput,
    ProjectService,
    ProjectView,
)

router = APIRouter(prefix="/projects")


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project",
)
async def get_project(
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    project = await project_service.get_project(context)
    return _project_response(project)


@router.get(
    "/{project_id}/members",
    response_model=ProjectMemberListResponse,
    summary="List project members",
)
async def list_project_members(
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectMemberListResponse:
    members = await project_service.list_members(context)
    return ProjectMemberListResponse(
        members=[ProjectMemberResponse.model_validate(member) for member in members]
    )


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add project member",
)
async def add_project_member(
    request: ProjectMemberCreateRequest,
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectMemberResponse:
    member = await project_service.add_member(
        context,
        ProjectMemberInput(user_id=request.user_id, role=request.role),
    )
    return ProjectMemberResponse.model_validate(member)


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove project member",
)
async def remove_project_member(
    user_id: UUID,
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> Response:
    await project_service.remove_member(context, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _project_response(project: ProjectView) -> ProjectResponse:
    return ProjectResponse(
        id=project.project.id,
        organization_id=project.project.organization_id,
        name=project.project.name,
        description=project.project.description,
        created_by_user_id=project.project.created_by_user_id,
        effective_role=project.effective_role,
        permissions=list(project.permissions),
        created_at=project.project.created_at,
        updated_at=project.project.updated_at,
    )
