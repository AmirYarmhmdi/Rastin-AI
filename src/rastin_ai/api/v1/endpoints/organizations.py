"""Organization and organization membership endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from rastin_ai.api.dependencies import (
    get_organization_access_context,
    get_organization_service,
    get_project_service,
)
from rastin_ai.schemas.organizations import (
    OrganizationCreateRequest,
    OrganizationListResponse,
    OrganizationMemberCreateRequest,
    OrganizationMemberListResponse,
    OrganizationMemberResponse,
    OrganizationResponse,
)
from rastin_ai.schemas.projects import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
)
from rastin_ai.services.authorization import OrganizationAccessContext
from rastin_ai.services.organizations import (
    OrganizationInput,
    OrganizationMemberInput,
    OrganizationService,
)
from rastin_ai.services.projects import ProjectInput, ProjectService, ProjectView

router = APIRouter(prefix="/organizations")


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create organization",
)
async def create_organization(
    request: OrganizationCreateRequest,
    organization_service: Annotated[
        OrganizationService,
        Depends(get_organization_service),
    ],
) -> OrganizationResponse:
    organization = await organization_service.create_organization(
        OrganizationInput(name=request.name, slug=request.slug)
    )
    return OrganizationResponse.model_validate(organization)


@router.get(
    "",
    response_model=OrganizationListResponse,
    summary="List organizations",
)
async def list_organizations(
    organization_service: Annotated[
        OrganizationService,
        Depends(get_organization_service),
    ],
) -> OrganizationListResponse:
    organizations = await organization_service.list_organizations()
    return OrganizationListResponse(
        organizations=[
            OrganizationResponse.model_validate(organization)
            for organization in organizations
        ]
    )


@router.get(
    "/{organization_id}/members",
    response_model=OrganizationMemberListResponse,
    summary="List organization members",
)
async def list_organization_members(
    context: Annotated[
        OrganizationAccessContext,
        Depends(get_organization_access_context),
    ],
    organization_service: Annotated[
        OrganizationService,
        Depends(get_organization_service),
    ],
) -> OrganizationMemberListResponse:
    members = await organization_service.list_members(context)
    return OrganizationMemberListResponse(
        members=[
            OrganizationMemberResponse.model_validate(member) for member in members
        ]
    )


@router.post(
    "/{organization_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add organization member",
)
async def add_organization_member(
    request: OrganizationMemberCreateRequest,
    context: Annotated[
        OrganizationAccessContext,
        Depends(get_organization_access_context),
    ],
    organization_service: Annotated[
        OrganizationService,
        Depends(get_organization_service),
    ],
) -> OrganizationMemberResponse:
    member = await organization_service.add_member(
        context,
        OrganizationMemberInput(user_id=request.user_id, role=request.role),
    )
    return OrganizationMemberResponse.model_validate(member)


@router.get(
    "/{organization_id}/projects",
    response_model=ProjectListResponse,
    summary="List organization projects",
)
async def list_organization_projects(
    context: Annotated[
        OrganizationAccessContext,
        Depends(get_organization_access_context),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectListResponse:
    projects = await project_service.list_projects(context)
    return ProjectListResponse(
        projects=[_project_response(project) for project in projects]
    )


@router.post(
    "/{organization_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create organization project",
)
async def create_organization_project(
    request: ProjectCreateRequest,
    context: Annotated[
        OrganizationAccessContext,
        Depends(get_organization_access_context),
    ],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> ProjectResponse:
    project = await project_service.create_project(
        context,
        ProjectInput(name=request.name, description=request.description),
    )
    return _project_response(project)


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
