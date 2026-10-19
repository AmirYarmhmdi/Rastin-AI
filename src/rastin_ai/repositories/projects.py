"""Repositories for projects and project memberships."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from rastin_ai.database.enums import OrganizationMemberRole, ProjectMemberRole
from rastin_ai.database.models.organization import Organization
from rastin_ai.database.models.organization_member import OrganizationMember
from rastin_ai.database.models.project import Project
from rastin_ai.database.models.project_member import ProjectMember
from rastin_ai.database.models.user import User
from rastin_ai.repositories.organizations import (
    OrganizationMemberRecord,
    OrganizationRecord,
    RepositoryConflictError,
)


@dataclass(frozen=True)
class ProjectCreate:
    organization_id: UUID
    name: str
    description: str | None
    created_by_user_id: UUID


@dataclass(frozen=True)
class ProjectRecord:
    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProjectMemberRecord:
    id: UUID
    project_id: UUID
    user_id: UUID
    role: str
    user_is_active: bool
    user_email: str | None
    user_display_name: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ProjectAccessRecord:
    organization: OrganizationRecord
    project: ProjectRecord
    organization_membership: OrganizationMemberRecord
    project_membership: ProjectMemberRecord | None


class ProjectRepository(Protocol):
    async def create_with_admin(
        self,
        project: ProjectCreate,
    ) -> tuple[ProjectRecord, ProjectMemberRecord]:
        """Create a project and explicit admin membership atomically."""

    async def list_accessible_for_user(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
    ) -> list[ProjectAccessRecord]:
        """Return organization projects visible to a user."""

    async def get_access_context(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
    ) -> ProjectAccessRecord | None:
        """Return scoped project access for a user."""

    async def list_members(self, project_id: UUID) -> list[ProjectMemberRecord]:
        """Return project members."""

    async def get_member(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
    ) -> ProjectMemberRecord | None:
        """Return one project membership."""

    async def add_member(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        role: ProjectMemberRole,
    ) -> ProjectMemberRecord:
        """Add a user to a project."""

    async def remove_member(self, project_id: UUID, *, user_id: UUID) -> bool:
        """Remove a project membership if present."""

    async def count_admin_members(self, project_id: UUID) -> int:
        """Count explicit project admin memberships."""


class SQLAlchemyProjectRepository:
    """SQLAlchemy-backed project repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_with_admin(
        self,
        project: ProjectCreate,
    ) -> tuple[ProjectRecord, ProjectMemberRecord]:
        project_model = Project(
            id=uuid4(),
            organization_id=project.organization_id,
            name=project.name,
            description=project.description,
            created_by_user_id=project.created_by_user_id,
        )
        member_model = ProjectMember(
            id=uuid4(),
            project=project_model,
            user_id=project.created_by_user_id,
            role=ProjectMemberRole.ADMIN.value,
        )
        self._session.add(member_model)
        try:
            await self._session.flush()
            await self._session.refresh(project_model)
            await self._session.refresh(member_model)
            created = _project_record(project_model)
            admin = await self._member_record(member_model.id)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise RepositoryConflictError("Project already exists.") from exc
        except Exception:
            await self._session.rollback()
            raise

        return created, admin

    async def list_accessible_for_user(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
    ) -> list[ProjectAccessRecord]:
        result = await self._session.execute(
            self._access_select(user_id)
            .where(Project.organization_id == organization_id)
            .order_by(Project.created_at.desc())
        )
        return [_access_record(*row) for row in result.all()]

    async def get_access_context(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
    ) -> ProjectAccessRecord | None:
        result = await self._session.execute(
            self._access_select(user_id).where(Project.id == project_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return _access_record(*row)

    async def list_members(self, project_id: UUID) -> list[ProjectMemberRecord]:
        result = await self._session.execute(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.created_at.asc())
        )
        return [_project_member_record(member, user) for member, user in result.all()]

    async def get_member(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
    ) -> ProjectMemberRecord | None:
        result = await self._session.execute(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        member, user = row
        return _project_member_record(member, user)

    async def add_member(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        role: ProjectMemberRole,
    ) -> ProjectMemberRecord:
        member = ProjectMember(
            id=uuid4(),
            project_id=project_id,
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
            raise RepositoryConflictError("Project membership already exists.") from exc
        except Exception:
            await self._session.rollback()
            raise

        return created

    async def remove_member(self, project_id: UUID, *, user_id: UUID) -> bool:
        result = await self._session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if member is None:
            return False

        try:
            await self._session.delete(member)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return True

    async def count_admin_members(self, project_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(ProjectMember)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.role == ProjectMemberRole.ADMIN.value,
            )
        )
        return int(result.scalar_one())

    def _access_select(self, user_id: UUID):
        project_member = ProjectMember
        organization_user = aliased(User)
        project_user = aliased(User)
        return (
            select(
                Organization,
                Project,
                OrganizationMember,
                organization_user,
                project_member,
                project_user,
            )
            .join(Organization, Organization.id == Project.organization_id)
            .join(
                OrganizationMember,
                and_(
                    OrganizationMember.organization_id == Organization.id,
                    OrganizationMember.user_id == user_id,
                ),
            )
            .join(organization_user, organization_user.id == OrganizationMember.user_id)
            .outerjoin(
                project_member,
                and_(
                    project_member.project_id == Project.id,
                    project_member.user_id == user_id,
                ),
            )
            .outerjoin(project_user, project_user.id == project_member.user_id)
            .where(
                or_(
                    OrganizationMember.role == OrganizationMemberRole.OWNER.value,
                    project_member.id.is_not(None),
                )
            )
        )

    async def _member_record(self, member_id: UUID) -> ProjectMemberRecord:
        result = await self._session.execute(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.id == member_id)
        )
        member, user = result.one()
        return _project_member_record(member, user)


def _project_record(project: Project) -> ProjectRecord:
    return ProjectRecord(
        id=project.id,
        organization_id=project.organization_id,
        name=project.name,
        description=project.description,
        created_by_user_id=project.created_by_user_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _project_member_record(member: ProjectMember, user: User) -> ProjectMemberRecord:
    return ProjectMemberRecord(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        role=member.role,
        user_is_active=user.is_active,
        user_email=user.email,
        user_display_name=user.display_name,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


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


def _access_record(
    organization: Organization,
    project: Project,
    organization_member: OrganizationMember,
    organization_user: User,
    project_member: ProjectMember | None,
    project_user: User | None,
) -> ProjectAccessRecord:
    return ProjectAccessRecord(
        organization=_organization_record(organization),
        project=_project_record(project),
        organization_membership=_organization_member_record(
            organization_member,
            organization_user,
        ),
        project_membership=(
            _project_member_record(project_member, project_user)
            if project_member is not None and project_user is not None
            else None
        ),
    )
