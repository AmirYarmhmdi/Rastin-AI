"""Organization application service."""

import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from fastapi import status

from rastin_ai.core.exceptions import AppException
from rastin_ai.database.enums import OrganizationMemberRole
from rastin_ai.repositories.organizations import (
    OrganizationCreate,
    OrganizationMemberRecord,
    OrganizationRecord,
    OrganizationRepository,
    RepositoryConflictError,
)
from rastin_ai.repositories.users import UserRepository
from rastin_ai.security.auth import AuthenticatedPrincipal
from rastin_ai.services.authorization import (
    AuthorizationService,
    OrganizationAccessContext,
)


class OrganizationConflictError(AppException):
    """Raised when an organization or membership already exists."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="ORGANIZATION_CONFLICT",
        )


class OrganizationMemberNotFoundError(AppException):
    """Raised when adding a missing or inactive user to an organization."""

    def __init__(self, user_id: UUID) -> None:
        super().__init__(
            "User not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="USER_NOT_FOUND",
            details={"user_id": str(user_id)},
        )


@dataclass(frozen=True)
class OrganizationInput:
    name: str
    slug: str | None = None


@dataclass(frozen=True)
class OrganizationMemberInput:
    user_id: UUID
    role: OrganizationMemberRole = OrganizationMemberRole.MEMBER


class OrganizationService(Protocol):
    async def create_organization(
        self,
        organization: OrganizationInput,
    ) -> OrganizationRecord:
        """Create an organization owned by the current user."""

    async def list_organizations(self) -> list[OrganizationRecord]:
        """List organizations where the current user is a member."""

    async def list_members(
        self,
        context: OrganizationAccessContext,
    ) -> list[OrganizationMemberRecord]:
        """List organization members when the current user is an owner."""

    async def add_member(
        self,
        context: OrganizationAccessContext,
        member: OrganizationMemberInput,
    ) -> OrganizationMemberRecord:
        """Add an existing active user to an organization."""


class RepositoryOrganizationService:
    """Organization service backed by repository and authorization boundaries."""

    def __init__(
        self,
        *,
        organization_repository: OrganizationRepository,
        user_repository: UserRepository,
        authorization_service: AuthorizationService,
        principal: AuthenticatedPrincipal,
    ) -> None:
        self._organization_repository = organization_repository
        self._user_repository = user_repository
        self._authorization_service = authorization_service
        self._principal = principal

    async def create_organization(
        self,
        organization: OrganizationInput,
    ) -> OrganizationRecord:
        name = _required_text(organization.name, "Organization name is required.")
        slug = _normalize_slug(organization.slug or name)
        try:
            created, _owner = await self._organization_repository.create_with_owner(
                OrganizationCreate(
                    name=name,
                    slug=slug,
                    created_by_user_id=self._principal.user_id,
                )
            )
        except RepositoryConflictError as exc:
            raise OrganizationConflictError("Organization already exists.") from exc
        return created

    async def list_organizations(self) -> list[OrganizationRecord]:
        return await self._organization_repository.list_for_user(
            user_id=self._principal.user_id,
        )

    async def list_members(
        self,
        context: OrganizationAccessContext,
    ) -> list[OrganizationMemberRecord]:
        self._authorization_service.require_organization_owner(context)
        return await self._organization_repository.list_members(context.organization.id)

    async def add_member(
        self,
        context: OrganizationAccessContext,
        member: OrganizationMemberInput,
    ) -> OrganizationMemberRecord:
        self._authorization_service.require_organization_owner(context)
        user = await self._user_repository.get_by_id(member.user_id)
        if user is None or not user.is_active:
            raise OrganizationMemberNotFoundError(member.user_id)

        existing = await self._organization_repository.get_member(
            context.organization.id,
            user_id=member.user_id,
        )
        if existing is not None:
            raise OrganizationConflictError("Organization membership already exists.")

        try:
            return await self._organization_repository.add_member(
                context.organization.id,
                user_id=member.user_id,
                role=member.role,
            )
        except RepositoryConflictError as exc:
            raise OrganizationConflictError(
                "Organization membership already exists."
            ) from exc


def _required_text(value: str, message: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise AppException(
            message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_ORGANIZATION",
        )
    return normalized


def _normalize_slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not normalized:
        raise AppException(
            "Organization slug is required.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_ORGANIZATION",
        )
    return normalized[:120]
