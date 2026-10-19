"""Repositories for organizations and organization memberships."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rastin_ai.database.enums import OrganizationMemberRole
from rastin_ai.database.models.organization import Organization
from rastin_ai.database.models.organization_member import OrganizationMember
from rastin_ai.database.models.user import User


class RepositoryConflictError(ValueError):
    """Raised when a repository write violates a uniqueness constraint."""


@dataclass(frozen=True)
class OrganizationCreate:
    name: str
    slug: str
    created_by_user_id: UUID


@dataclass(frozen=True)
class OrganizationRecord:
    id: UUID
    name: str
    slug: str
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class OrganizationMemberRecord:
    id: UUID
    organization_id: UUID
    user_id: UUID
    role: str
    user_is_active: bool
    user_email: str | None
    user_display_name: str | None
    created_at: datetime
    updated_at: datetime


class OrganizationRepository(Protocol):
    async def create_with_owner(
        self,
        organization: OrganizationCreate,
    ) -> tuple[OrganizationRecord, OrganizationMemberRecord]:
        """Create an organization and owner membership atomically."""

    async def list_for_user(self, *, user_id: UUID) -> list[OrganizationRecord]:
        """Return organizations where the user is a member."""

    async def get_for_member(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
    ) -> tuple[OrganizationRecord, OrganizationMemberRecord] | None:
        """Return an organization only when the user is a member."""

    async def get_member(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
    ) -> OrganizationMemberRecord | None:
        """Return one organization membership."""

    async def list_members(
        self,
        organization_id: UUID,
    ) -> list[OrganizationMemberRecord]:
        """Return organization members."""

    async def add_member(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
        role: OrganizationMemberRole,
    ) -> OrganizationMemberRecord:
        """Add an existing user to an organization."""


class SQLAlchemyOrganizationRepository:
    """SQLAlchemy-backed organization repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_with_owner(
        self,
        organization: OrganizationCreate,
    ) -> tuple[OrganizationRecord, OrganizationMemberRecord]:
        organization_model = Organization(
            id=uuid4(),
            name=organization.name,
            slug=organization.slug,
            created_by_user_id=organization.created_by_user_id,
        )
        member_model = OrganizationMember(
            id=uuid4(),
            organization=organization_model,
            user_id=organization.created_by_user_id,
            role=OrganizationMemberRole.OWNER.value,
        )
        self._session.add(member_model)
        try:
            await self._session.flush()
            await self._session.refresh(organization_model)
            await self._session.refresh(member_model)
            created = _organization_record(organization_model)
            owner = await self._member_record(member_model.id)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise RepositoryConflictError("Organization already exists.") from exc
        except Exception:
            await self._session.rollback()
            raise

        return created, owner

    async def list_for_user(self, *, user_id: UUID) -> list[OrganizationRecord]:
        result = await self._session.execute(
            select(Organization)
            .join(OrganizationMember)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.created_at.desc())
        )
        return [_organization_record(record) for record in result.scalars().all()]

    async def get_for_member(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
    ) -> tuple[OrganizationRecord, OrganizationMemberRecord] | None:
        result = await self._session.execute(
            select(Organization, OrganizationMember, User)
            .join(
                OrganizationMember,
                OrganizationMember.organization_id == Organization.id,
            )
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                Organization.id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None

        organization, member, user = row
        return _organization_record(organization), _organization_member_record(
            member,
            user,
        )

    async def get_member(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
    ) -> OrganizationMemberRecord | None:
        result = await self._session.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        member, user = row
        return _organization_member_record(member, user)

    async def list_members(
        self,
        organization_id: UUID,
    ) -> list[OrganizationMemberRecord]:
        result = await self._session.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(OrganizationMember.created_at.asc())
        )
        return [
            _organization_member_record(member, user) for member, user in result.all()
        ]

    async def add_member(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
        role: OrganizationMemberRole,
    ) -> OrganizationMemberRecord:
        member = OrganizationMember(
            id=uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            role=role.value,
        )
        self._session.add(member)
        try:
            await self._session.flush()
            await self._session.refresh(member)
            created = await self._member_record(member.id)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise RepositoryConflictError(
                "Organization membership already exists."
            ) from exc
        except Exception:
            await self._session.rollback()
            raise

        return created

    async def _member_record(self, member_id: UUID) -> OrganizationMemberRecord:
        result = await self._session.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.id == member_id)
        )
        member, user = result.one()
        return _organization_member_record(member, user)


def _organization_record(organization: Organization) -> OrganizationRecord:
    return OrganizationRecord(
        id=organization.id,
        name=organization.name,
        slug=organization.slug,
        created_by_user_id=organization.created_by_user_id,
        created_at=organization.created_at,
        updated_at=organization.updated_at,
    )


def _organization_member_record(
    member: OrganizationMember,
    user: User,
) -> OrganizationMemberRecord:
    return OrganizationMemberRecord(
        id=member.id,
        organization_id=member.organization_id,
        user_id=member.user_id,
        role=member.role,
        user_is_active=user.is_active,
        user_email=user.email,
        user_display_name=user.display_name,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )
