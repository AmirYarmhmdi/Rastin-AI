"""Centralized organization and project authorization policies."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import status

from rastin_ai.core.exceptions import AppException
from rastin_ai.database.enums import OrganizationMemberRole, ProjectMemberRole
from rastin_ai.repositories.organizations import (
    OrganizationMemberRecord,
    OrganizationRecord,
    OrganizationRepository,
)
from rastin_ai.repositories.projects import (
    ProjectAccessRecord,
    ProjectMemberRecord,
    ProjectRecord,
    ProjectRepository,
)
from rastin_ai.security.auth import AuthenticatedPrincipal

PROJECT_PERMISSION_READ = "projects.read"
PROJECT_PERMISSION_MANAGE_MEMBERS = "projects.manage_members"
PROJECT_PERMISSION_DOCUMENTS_UPLOAD = "documents.upload"
PROJECT_PERMISSION_CHATS_CREATE = "chats.create"


class OrganizationNotFoundError(AppException):
    """Raised when the current user cannot access an organization."""

    def __init__(self, organization_id: UUID) -> None:
        super().__init__(
            "Organization not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="ORGANIZATION_NOT_FOUND",
            details={"organization_id": str(organization_id)},
        )


class ProjectNotFoundError(AppException):
    """Raised when the current user cannot access a project."""

    def __init__(self, project_id: UUID) -> None:
        super().__init__(
            "Project not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="PROJECT_NOT_FOUND",
            details={"project_id": str(project_id)},
        )


class AuthorizationForbiddenError(AppException):
    """Raised when the user is known but lacks a required role."""

    def __init__(self, message: str = "Insufficient permissions.") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="INSUFFICIENT_PERMISSIONS",
        )


@dataclass(frozen=True)
class OrganizationAccessContext:
    principal: AuthenticatedPrincipal
    organization: OrganizationRecord
    organization_membership: OrganizationMemberRecord


@dataclass(frozen=True)
class ProjectAccessContext:
    principal: AuthenticatedPrincipal
    organization: OrganizationRecord
    project: ProjectRecord
    organization_membership: OrganizationMemberRecord
    project_membership: ProjectMemberRecord | None
    effective_project_role: str

    @property
    def permissions(self) -> tuple[str, ...]:
        return permissions_for_project_role(self.effective_project_role)


class AuthorizationService:
    """Resolve access contexts and apply fixed role policies."""

    def __init__(
        self,
        *,
        organization_repository: OrganizationRepository,
        project_repository: ProjectRepository,
    ) -> None:
        self._organization_repository = organization_repository
        self._project_repository = project_repository

    async def organization_context(
        self,
        organization_id: UUID,
        *,
        principal: AuthenticatedPrincipal,
    ) -> OrganizationAccessContext:
        access = await self._organization_repository.get_for_member(
            organization_id,
            user_id=principal.user_id,
        )
        if access is None:
            raise OrganizationNotFoundError(organization_id)
        organization, membership = access
        return OrganizationAccessContext(
            principal=principal,
            organization=organization,
            organization_membership=membership,
        )

    async def project_context(
        self,
        project_id: UUID,
        *,
        principal: AuthenticatedPrincipal,
    ) -> ProjectAccessContext:
        access = await self._project_repository.get_access_context(
            project_id,
            user_id=principal.user_id,
        )
        if access is None:
            raise ProjectNotFoundError(project_id)
        return _project_context(principal, access)

    def require_organization_owner(self, context: OrganizationAccessContext) -> None:
        if context.organization_membership.role != OrganizationMemberRole.OWNER.value:
            raise AuthorizationForbiddenError(
                "Organization owner permissions are required."
            )

    def require_project_admin(self, context: ProjectAccessContext) -> None:
        if context.effective_project_role != ProjectMemberRole.ADMIN.value:
            raise AuthorizationForbiddenError("Project admin permissions are required.")

    def require_project_permission(
        self,
        context: ProjectAccessContext,
        permission: str,
    ) -> None:
        if permission not in context.permissions:
            raise AuthorizationForbiddenError("Project permission is required.")


def permissions_for_project_role(role: str) -> tuple[str, ...]:
    if role == ProjectMemberRole.ADMIN.value:
        return (
            PROJECT_PERMISSION_READ,
            PROJECT_PERMISSION_MANAGE_MEMBERS,
            PROJECT_PERMISSION_DOCUMENTS_UPLOAD,
            PROJECT_PERMISSION_CHATS_CREATE,
        )
    if role == ProjectMemberRole.MEMBER.value:
        return (
            PROJECT_PERMISSION_READ,
            PROJECT_PERMISSION_DOCUMENTS_UPLOAD,
            PROJECT_PERMISSION_CHATS_CREATE,
        )
    if role == ProjectMemberRole.VIEWER.value:
        return (PROJECT_PERMISSION_READ,)
    return ()


def _project_context(
    principal: AuthenticatedPrincipal,
    access: ProjectAccessRecord,
) -> ProjectAccessContext:
    effective_role = (
        ProjectMemberRole.ADMIN.value
        if access.organization_membership.role == OrganizationMemberRole.OWNER.value
        else _require_project_membership(access).role
    )
    return ProjectAccessContext(
        principal=principal,
        organization=access.organization,
        project=access.project,
        organization_membership=access.organization_membership,
        project_membership=access.project_membership,
        effective_project_role=effective_role,
    )


def _require_project_membership(access: ProjectAccessRecord) -> ProjectMemberRecord:
    if access.project_membership is None:
        raise ProjectNotFoundError(access.project.id)
    return access.project_membership
