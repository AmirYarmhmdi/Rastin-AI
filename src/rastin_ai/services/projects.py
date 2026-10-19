"""Project application service."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from fastapi import status

from rastin_ai.core.exceptions import AppException
from rastin_ai.database.enums import OrganizationMemberRole, ProjectMemberRole
from rastin_ai.repositories.organizations import (
    OrganizationRepository,
    RepositoryConflictError,
)
from rastin_ai.repositories.projects import (
    ProjectCreate,
    ProjectMemberRecord,
    ProjectRecord,
    ProjectRepository,
)
from rastin_ai.security.auth import AuthenticatedPrincipal
from rastin_ai.services.authorization import (
    AuthorizationService,
    OrganizationAccessContext,
    ProjectAccessContext,
    permissions_for_project_role,
)


class ProjectMembershipConflictError(AppException):
    """Raised when a project membership already exists."""

    def __init__(self) -> None:
        super().__init__(
            "Project membership already exists.",
            status_code=status.HTTP_409_CONFLICT,
            error_code="PROJECT_MEMBERSHIP_CONFLICT",
        )


class ProjectMembershipTargetError(AppException):
    """Raised when the target user cannot be added to a project."""

    def __init__(self, user_id: UUID) -> None:
        super().__init__(
            "User must be an active member of the project organization.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="PROJECT_MEMBER_REQUIRES_ORGANIZATION_MEMBER",
            details={"user_id": str(user_id)},
        )


class ProjectMembershipNotFoundError(AppException):
    """Raised when removing a project member that does not exist."""

    def __init__(self, user_id: UUID) -> None:
        super().__init__(
            "Project membership not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="PROJECT_MEMBERSHIP_NOT_FOUND",
            details={"user_id": str(user_id)},
        )


class FinalProjectAdminError(AppException):
    """Raised when removing the last explicit project admin."""

    def __init__(self) -> None:
        super().__init__(
            "At least one explicit project admin membership is required.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="PROJECT_REQUIRES_ADMIN",
        )


@dataclass(frozen=True)
class ProjectInput:
    name: str
    description: str | None = None


@dataclass(frozen=True)
class ProjectMemberInput:
    user_id: UUID
    role: ProjectMemberRole


@dataclass(frozen=True)
class ProjectView:
    project: ProjectRecord
    effective_role: str
    permissions: tuple[str, ...]


class ProjectService(Protocol):
    async def list_projects(
        self,
        context: OrganizationAccessContext,
    ) -> list[ProjectView]:
        """List projects accessible to the current user."""

    async def create_project(
        self,
        context: OrganizationAccessContext,
        project: ProjectInput,
    ) -> ProjectView:
        """Create a project in an organization."""

    async def get_project(self, context: ProjectAccessContext) -> ProjectView:
        """Return project metadata and effective access."""

    async def list_members(
        self,
        context: ProjectAccessContext,
    ) -> list[ProjectMemberRecord]:
        """List project members for project admins."""

    async def add_member(
        self,
        context: ProjectAccessContext,
        member: ProjectMemberInput,
    ) -> ProjectMemberRecord:
        """Add an organization member to a project."""

    async def remove_member(
        self,
        context: ProjectAccessContext,
        user_id: UUID,
    ) -> None:
        """Remove a project member."""


class RepositoryProjectService:
    """Project service backed by repository and authorization boundaries."""

    def __init__(
        self,
        *,
        project_repository: ProjectRepository,
        organization_repository: OrganizationRepository,
        authorization_service: AuthorizationService,
        principal: AuthenticatedPrincipal,
    ) -> None:
        self._project_repository = project_repository
        self._organization_repository = organization_repository
        self._authorization_service = authorization_service
        self._principal = principal

    async def list_projects(
        self,
        context: OrganizationAccessContext,
    ) -> list[ProjectView]:
        records = await self._project_repository.list_accessible_for_user(
            context.organization.id,
            user_id=self._principal.user_id,
        )
        views = []
        for record in records:
            if (
                record.organization_membership.role
                == OrganizationMemberRole.OWNER.value
            ):
                effective_role = ProjectMemberRole.ADMIN.value
            elif record.project_membership is not None:
                effective_role = record.project_membership.role
            else:
                continue
            views.append(
                ProjectView(
                    project=record.project,
                    effective_role=effective_role,
                    permissions=permissions_for_project_role(effective_role),
                )
            )
        return views

    async def create_project(
        self,
        context: OrganizationAccessContext,
        project: ProjectInput,
    ) -> ProjectView:
        self._authorization_service.require_organization_owner(context)
        name = _required_text(project.name)
        description = project.description.strip() if project.description else None
        created, _admin = await self._project_repository.create_with_admin(
            ProjectCreate(
                organization_id=context.organization.id,
                name=name,
                description=description or None,
                created_by_user_id=self._principal.user_id,
            )
        )
        return ProjectView(
            project=created,
            effective_role=ProjectMemberRole.ADMIN.value,
            permissions=ProjectAccessContext(
                principal=self._principal,
                organization=context.organization,
                project=created,
                organization_membership=context.organization_membership,
                project_membership=None,
                effective_project_role=ProjectMemberRole.ADMIN.value,
            ).permissions,
        )

    async def get_project(self, context: ProjectAccessContext) -> ProjectView:
        return ProjectView(
            project=context.project,
            effective_role=context.effective_project_role,
            permissions=context.permissions,
        )

    async def list_members(
        self,
        context: ProjectAccessContext,
    ) -> list[ProjectMemberRecord]:
        self._authorization_service.require_project_admin(context)
        return await self._project_repository.list_members(context.project.id)

    async def add_member(
        self,
        context: ProjectAccessContext,
        member: ProjectMemberInput,
    ) -> ProjectMemberRecord:
        self._authorization_service.require_project_admin(context)
        organization_member = await self._organization_repository.get_member(
            context.organization.id,
            user_id=member.user_id,
        )
        if organization_member is None or not organization_member.user_is_active:
            raise ProjectMembershipTargetError(member.user_id)

        existing = await self._project_repository.get_member(
            context.project.id,
            user_id=member.user_id,
        )
        if existing is not None:
            raise ProjectMembershipConflictError()

        try:
            return await self._project_repository.add_member(
                context.project.id,
                user_id=member.user_id,
                role=member.role,
            )
        except RepositoryConflictError as exc:
            raise ProjectMembershipConflictError() from exc

    async def remove_member(
        self,
        context: ProjectAccessContext,
        user_id: UUID,
    ) -> None:
        self._authorization_service.require_project_admin(context)
        member = await self._project_repository.get_member(
            context.project.id,
            user_id=user_id,
        )
        if member is None:
            raise ProjectMembershipNotFoundError(user_id)

        if member.role == ProjectMemberRole.ADMIN.value:
            admin_count = await self._project_repository.count_admin_members(
                context.project.id
            )
            if admin_count <= 1:
                raise FinalProjectAdminError()

        removed = await self._project_repository.remove_member(
            context.project.id,
            user_id=user_id,
        )
        if not removed:
            raise ProjectMembershipNotFoundError(user_id)


def _required_text(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise AppException(
            "Project name is required.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_PROJECT",
        )
    return normalized
