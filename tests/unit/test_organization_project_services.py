"""Tests for organization/project services and authorization policy."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from rastin_ai.database.enums import OrganizationMemberRole, ProjectMemberRole
from rastin_ai.repositories.organizations import (
    OrganizationCreate,
    OrganizationMemberRecord,
    OrganizationRecord,
    RepositoryConflictError,
)
from rastin_ai.repositories.projects import (
    ProjectAccessRecord,
    ProjectCreate,
    ProjectMemberRecord,
    ProjectRecord,
)
from rastin_ai.repositories.users import UserRecord
from rastin_ai.security.auth import AuthenticatedPrincipal
from rastin_ai.services.authorization import (
    AuthorizationForbiddenError,
    AuthorizationService,
    ProjectNotFoundError,
)
from rastin_ai.services.organizations import (
    OrganizationConflictError,
    OrganizationInput,
    OrganizationMemberInput,
    OrganizationMemberNotFoundError,
    RepositoryOrganizationService,
)
from rastin_ai.services.projects import (
    FinalProjectAdminError,
    ProjectInput,
    ProjectMemberInput,
    ProjectMembershipConflictError,
    ProjectMembershipTargetError,
    RepositoryProjectService,
)

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
OWNER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
ADMIN_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
MEMBER_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
VIEWER_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
OUTSIDER_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")


def test_create_organization_creates_owner_membership() -> None:
    org_repo = FakeOrganizationRepository()
    service = _organization_service(org_repo, principal=_principal(OWNER_ID))

    organization = _run(service.create_organization(OrganizationInput(name="Acme")))

    assert organization.name == "Acme"
    owner = org_repo.members[(organization.id, OWNER_ID)]
    assert owner.role == OrganizationMemberRole.OWNER.value


def test_user_lists_only_organizations_where_they_are_a_member() -> None:
    org_repo = FakeOrganizationRepository()
    acme = org_repo.seed_organization("Acme", owner_id=OWNER_ID)
    other = org_repo.seed_organization("Other", owner_id=OUTSIDER_ID)
    org_repo.seed_member(acme.id, MEMBER_ID, OrganizationMemberRole.MEMBER)

    service = _organization_service(org_repo, principal=_principal(MEMBER_ID))

    assert _run(service.list_organizations()) == [acme]
    assert other not in _run(service.list_organizations())


def test_create_project_creates_explicit_project_admin_membership() -> None:
    org_repo = FakeOrganizationRepository()
    project_repo = FakeProjectRepository(org_repo)
    organization = org_repo.seed_organization("Acme", owner_id=OWNER_ID)
    service = _project_service(
        org_repo,
        project_repo,
        principal=_principal(OWNER_ID),
    )
    context = _run(
        _authorization(org_repo, project_repo).organization_context(
            organization.id,
            principal=_principal(OWNER_ID),
        )
    )

    project = _run(service.create_project(context, ProjectInput(name="Apollo")))

    assert project.effective_role == ProjectMemberRole.ADMIN.value
    admin = project_repo.members[(project.project.id, OWNER_ID)]
    assert admin.role == ProjectMemberRole.ADMIN.value


def test_organization_owner_has_implicit_project_admin_access() -> None:
    org_repo = FakeOrganizationRepository()
    project_repo = FakeProjectRepository(org_repo)
    organization = org_repo.seed_organization("Acme", owner_id=OWNER_ID)
    project = project_repo.seed_project(organization.id, created_by_user_id=ADMIN_ID)

    context = _run(
        _authorization(org_repo, project_repo).project_context(
            project.id,
            principal=_principal(OWNER_ID),
        )
    )

    assert context.project_membership is None
    assert context.effective_project_role == ProjectMemberRole.ADMIN.value
    assert "projects.manage_members" in context.permissions


def test_cross_organization_project_access_is_non_disclosing() -> None:
    org_repo = FakeOrganizationRepository()
    project_repo = FakeProjectRepository(org_repo)
    organization = org_repo.seed_organization("Acme", owner_id=OWNER_ID)
    project = project_repo.seed_project(organization.id, created_by_user_id=OWNER_ID)

    with pytest.raises(ProjectNotFoundError) as exc_info:
        _run(
            _authorization(org_repo, project_repo).project_context(
                project.id,
                principal=_principal(OUTSIDER_ID),
            )
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.error_code == "PROJECT_NOT_FOUND"


def test_project_member_must_be_active_member_of_same_organization() -> None:
    org_repo = FakeOrganizationRepository()
    project_repo = FakeProjectRepository(org_repo)
    organization = org_repo.seed_organization("Acme", owner_id=OWNER_ID)
    project = project_repo.seed_project(organization.id, created_by_user_id=OWNER_ID)
    project_repo.seed_member(project.id, OWNER_ID, ProjectMemberRole.ADMIN)
    service = _project_service(org_repo, project_repo, principal=_principal(OWNER_ID))
    context = _run(
        _authorization(org_repo, project_repo).project_context(
            project.id,
            principal=_principal(OWNER_ID),
        )
    )

    with pytest.raises(ProjectMembershipTargetError):
        _run(
            service.add_member(
                context,
                ProjectMemberInput(user_id=OUTSIDER_ID, role=ProjectMemberRole.MEMBER),
            )
        )

    org_repo.users[OUTSIDER_ID] = _user(OUTSIDER_ID, is_active=False)
    org_repo.seed_member(organization.id, OUTSIDER_ID, OrganizationMemberRole.MEMBER)

    with pytest.raises(ProjectMembershipTargetError):
        _run(
            service.add_member(
                context,
                ProjectMemberInput(user_id=OUTSIDER_ID, role=ProjectMemberRole.MEMBER),
            )
        )


def test_project_admin_can_add_and_remove_project_members() -> None:
    org_repo = FakeOrganizationRepository()
    project_repo = FakeProjectRepository(org_repo)
    organization = org_repo.seed_organization("Acme", owner_id=OWNER_ID)
    org_repo.seed_member(organization.id, MEMBER_ID, OrganizationMemberRole.MEMBER)
    project = project_repo.seed_project(organization.id, created_by_user_id=OWNER_ID)
    project_repo.seed_member(project.id, OWNER_ID, ProjectMemberRole.ADMIN)
    service = _project_service(org_repo, project_repo, principal=_principal(OWNER_ID))
    context = _run(
        _authorization(org_repo, project_repo).project_context(
            project.id,
            principal=_principal(OWNER_ID),
        )
    )

    added = _run(
        service.add_member(
            context,
            ProjectMemberInput(user_id=MEMBER_ID, role=ProjectMemberRole.VIEWER),
        )
    )
    _run(service.remove_member(context, MEMBER_ID))

    assert added.role == ProjectMemberRole.VIEWER.value
    assert (project.id, MEMBER_ID) not in project_repo.members


def test_project_member_and_viewer_cannot_manage_members() -> None:
    org_repo = FakeOrganizationRepository()
    project_repo = FakeProjectRepository(org_repo)
    organization = org_repo.seed_organization("Acme", owner_id=OWNER_ID)
    for user_id, _project_role in (
        (MEMBER_ID, ProjectMemberRole.MEMBER),
        (VIEWER_ID, ProjectMemberRole.VIEWER),
    ):
        org_repo.seed_member(organization.id, user_id, OrganizationMemberRole.MEMBER)
    project = project_repo.seed_project(organization.id, created_by_user_id=OWNER_ID)
    project_repo.seed_member(project.id, OWNER_ID, ProjectMemberRole.ADMIN)
    project_repo.seed_member(project.id, MEMBER_ID, ProjectMemberRole.MEMBER)
    project_repo.seed_member(project.id, VIEWER_ID, ProjectMemberRole.VIEWER)

    for user_id in (MEMBER_ID, VIEWER_ID):
        context = _run(
            _authorization(org_repo, project_repo).project_context(
                project.id,
                principal=_principal(user_id),
            )
        )
        service = _project_service(
            org_repo, project_repo, principal=_principal(user_id)
        )
        with pytest.raises(AuthorizationForbiddenError):
            _run(service.list_members(context))


def test_duplicate_memberships_fail_safely() -> None:
    org_repo = FakeOrganizationRepository()
    organization = org_repo.seed_organization("Acme", owner_id=OWNER_ID)
    service = _organization_service(org_repo, principal=_principal(OWNER_ID))
    context = _run(
        _authorization(org_repo, FakeProjectRepository(org_repo)).organization_context(
            organization.id, principal=_principal(OWNER_ID)
        )
    )

    with pytest.raises(OrganizationConflictError):
        _run(
            service.add_member(
                context,
                OrganizationMemberInput(
                    user_id=OWNER_ID,
                    role=OrganizationMemberRole.MEMBER,
                ),
            )
        )

    project_repo = FakeProjectRepository(org_repo)
    project = project_repo.seed_project(organization.id, created_by_user_id=OWNER_ID)
    project_repo.seed_member(project.id, OWNER_ID, ProjectMemberRole.ADMIN)
    project_service = _project_service(
        org_repo,
        project_repo,
        principal=_principal(OWNER_ID),
    )
    project_context = _run(
        _authorization(org_repo, project_repo).project_context(
            project.id,
            principal=_principal(OWNER_ID),
        )
    )

    with pytest.raises(ProjectMembershipConflictError):
        _run(
            project_service.add_member(
                project_context,
                ProjectMemberInput(user_id=OWNER_ID, role=ProjectMemberRole.ADMIN),
            )
        )


def test_cannot_remove_final_explicit_project_admin() -> None:
    org_repo = FakeOrganizationRepository()
    project_repo = FakeProjectRepository(org_repo)
    organization = org_repo.seed_organization("Acme", owner_id=OWNER_ID)
    project = project_repo.seed_project(organization.id, created_by_user_id=OWNER_ID)
    project_repo.seed_member(project.id, OWNER_ID, ProjectMemberRole.ADMIN)
    service = _project_service(org_repo, project_repo, principal=_principal(OWNER_ID))
    context = _run(
        _authorization(org_repo, project_repo).project_context(
            project.id,
            principal=_principal(OWNER_ID),
        )
    )

    with pytest.raises(FinalProjectAdminError):
        _run(service.remove_member(context, OWNER_ID))


def test_project_admin_can_remove_self_when_another_admin_remains() -> None:
    org_repo = FakeOrganizationRepository()
    project_repo = FakeProjectRepository(org_repo)
    organization = org_repo.seed_organization("Acme", owner_id=OWNER_ID)
    org_repo.seed_member(organization.id, ADMIN_ID, OrganizationMemberRole.MEMBER)
    project = project_repo.seed_project(organization.id, created_by_user_id=OWNER_ID)
    project_repo.seed_member(project.id, OWNER_ID, ProjectMemberRole.ADMIN)
    project_repo.seed_member(project.id, ADMIN_ID, ProjectMemberRole.ADMIN)
    service = _project_service(org_repo, project_repo, principal=_principal(OWNER_ID))
    context = _run(
        _authorization(org_repo, project_repo).project_context(
            project.id,
            principal=_principal(OWNER_ID),
        )
    )

    _run(service.remove_member(context, OWNER_ID))

    assert (project.id, OWNER_ID) not in project_repo.members
    assert (
        project_repo.members[(project.id, ADMIN_ID)].role
        == ProjectMemberRole.ADMIN.value
    )


def test_organization_member_endpoint_requires_existing_active_user() -> None:
    org_repo = FakeOrganizationRepository()
    organization = org_repo.seed_organization("Acme", owner_id=OWNER_ID)
    service = _organization_service(org_repo, principal=_principal(OWNER_ID))
    context = _run(
        _authorization(org_repo, FakeProjectRepository(org_repo)).organization_context(
            organization.id, principal=_principal(OWNER_ID)
        )
    )

    with pytest.raises(OrganizationMemberNotFoundError):
        _run(
            service.add_member(
                context,
                OrganizationMemberInput(
                    user_id=OUTSIDER_ID,
                    role=OrganizationMemberRole.MEMBER,
                ),
            )
        )


class FakeUserRepository:
    def __init__(self, users: dict[UUID, UserRecord]) -> None:
        self._users = users

    async def get_by_id(self, user_id: UUID) -> UserRecord | None:
        return self._users.get(user_id)


class FakeOrganizationRepository:
    def __init__(self) -> None:
        self.organizations: dict[UUID, OrganizationRecord] = {}
        self.members: dict[tuple[UUID, UUID], OrganizationMemberRecord] = {}
        self.users: dict[UUID, UserRecord] = {
            OWNER_ID: _user(OWNER_ID),
            ADMIN_ID: _user(ADMIN_ID),
            MEMBER_ID: _user(MEMBER_ID),
            VIEWER_ID: _user(VIEWER_ID),
        }

    async def create_with_owner(
        self,
        organization: OrganizationCreate,
    ) -> tuple[OrganizationRecord, OrganizationMemberRecord]:
        if any(item.slug == organization.slug for item in self.organizations.values()):
            raise RepositoryConflictError("Organization already exists.")
        record = OrganizationRecord(
            id=uuid4(),
            name=organization.name,
            slug=organization.slug,
            created_by_user_id=organization.created_by_user_id,
            created_at=NOW,
            updated_at=NOW,
        )
        self.organizations[record.id] = record
        member = self.seed_member(
            record.id,
            organization.created_by_user_id,
            OrganizationMemberRole.OWNER,
        )
        return record, member

    async def list_for_user(self, *, user_id: UUID) -> list[OrganizationRecord]:
        return [
            self.organizations[organization_id]
            for organization_id, member_user_id in self.members
            if member_user_id == user_id
        ]

    async def get_for_member(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
    ) -> tuple[OrganizationRecord, OrganizationMemberRecord] | None:
        member = self.members.get((organization_id, user_id))
        organization = self.organizations.get(organization_id)
        if member is None or organization is None:
            return None
        return organization, member

    async def get_member(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
    ) -> OrganizationMemberRecord | None:
        return self.members.get((organization_id, user_id))

    async def list_members(
        self,
        organization_id: UUID,
    ) -> list[OrganizationMemberRecord]:
        return [
            member
            for (member_organization_id, _user_id), member in self.members.items()
            if member_organization_id == organization_id
        ]

    async def add_member(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
        role: OrganizationMemberRole,
    ) -> OrganizationMemberRecord:
        if (organization_id, user_id) in self.members:
            raise RepositoryConflictError("Organization membership already exists.")
        return self.seed_member(organization_id, user_id, role)

    def seed_organization(self, name: str, *, owner_id: UUID) -> OrganizationRecord:
        organization = OrganizationRecord(
            id=uuid4(),
            name=name,
            slug=name.lower(),
            created_by_user_id=owner_id,
            created_at=NOW,
            updated_at=NOW,
        )
        self.organizations[organization.id] = organization
        self.seed_member(organization.id, owner_id, OrganizationMemberRole.OWNER)
        return organization

    def seed_member(
        self,
        organization_id: UUID,
        user_id: UUID,
        role: OrganizationMemberRole,
    ) -> OrganizationMemberRecord:
        user = self.users.setdefault(user_id, _user(user_id))
        member = OrganizationMemberRecord(
            id=uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            role=role.value,
            user_is_active=user.is_active,
            user_email=user.email,
            user_display_name=user.display_name,
            created_at=NOW,
            updated_at=NOW,
        )
        self.members[(organization_id, user_id)] = member
        return member


class FakeProjectRepository:
    def __init__(self, organization_repository: FakeOrganizationRepository) -> None:
        self._organization_repository = organization_repository
        self.projects: dict[UUID, ProjectRecord] = {}
        self.members: dict[tuple[UUID, UUID], ProjectMemberRecord] = {}

    async def create_with_admin(
        self,
        project: ProjectCreate,
    ) -> tuple[ProjectRecord, ProjectMemberRecord]:
        record = self.seed_project(
            project.organization_id,
            created_by_user_id=project.created_by_user_id,
            name=project.name,
            description=project.description,
        )
        member = self.seed_member(
            record.id,
            project.created_by_user_id,
            ProjectMemberRole.ADMIN,
        )
        return record, member

    async def list_accessible_for_user(
        self,
        organization_id: UUID,
        *,
        user_id: UUID,
    ) -> list[ProjectAccessRecord]:
        records = []
        for project in self.projects.values():
            if project.organization_id == organization_id:
                access = await self.get_access_context(project.id, user_id=user_id)
                if access is not None:
                    records.append(access)
        return records

    async def get_access_context(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
    ) -> ProjectAccessRecord | None:
        project = self.projects.get(project_id)
        if project is None:
            return None
        organization = self._organization_repository.organizations[
            project.organization_id
        ]
        organization_member = self._organization_repository.members.get(
            (organization.id, user_id)
        )
        if organization_member is None:
            return None
        project_member = self.members.get((project_id, user_id))
        if (
            organization_member.role != OrganizationMemberRole.OWNER.value
            and project_member is None
        ):
            return None
        return ProjectAccessRecord(
            organization=organization,
            project=project,
            organization_membership=organization_member,
            project_membership=project_member,
        )

    async def list_members(self, project_id: UUID) -> list[ProjectMemberRecord]:
        return [
            member
            for (member_project_id, _user_id), member in self.members.items()
            if member_project_id == project_id
        ]

    async def get_member(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
    ) -> ProjectMemberRecord | None:
        return self.members.get((project_id, user_id))

    async def add_member(
        self,
        project_id: UUID,
        *,
        user_id: UUID,
        role: ProjectMemberRole,
    ) -> ProjectMemberRecord:
        if (project_id, user_id) in self.members:
            raise RepositoryConflictError("Project membership already exists.")
        return self.seed_member(project_id, user_id, role)

    async def remove_member(self, project_id: UUID, *, user_id: UUID) -> bool:
        return self.members.pop((project_id, user_id), None) is not None

    async def count_admin_members(self, project_id: UUID) -> int:
        return sum(
            1
            for (member_project_id, _user_id), member in self.members.items()
            if member_project_id == project_id
            and member.role == ProjectMemberRole.ADMIN.value
        )

    def seed_project(
        self,
        organization_id: UUID,
        *,
        created_by_user_id: UUID,
        name: str = "Apollo",
        description: str | None = None,
    ) -> ProjectRecord:
        project = ProjectRecord(
            id=uuid4(),
            organization_id=organization_id,
            name=name,
            description=description,
            created_by_user_id=created_by_user_id,
            created_at=NOW,
            updated_at=NOW,
        )
        self.projects[project.id] = project
        return project

    def seed_member(
        self,
        project_id: UUID,
        user_id: UUID,
        role: ProjectMemberRole,
    ) -> ProjectMemberRecord:
        user = self._organization_repository.users.setdefault(user_id, _user(user_id))
        member = ProjectMemberRecord(
            id=uuid4(),
            project_id=project_id,
            user_id=user_id,
            role=role.value,
            user_is_active=user.is_active,
            user_email=user.email,
            user_display_name=user.display_name,
            created_at=NOW,
            updated_at=NOW,
        )
        self.members[(project_id, user_id)] = member
        return member


def _organization_service(
    organization_repository: FakeOrganizationRepository,
    *,
    principal: AuthenticatedPrincipal,
) -> RepositoryOrganizationService:
    project_repository = FakeProjectRepository(organization_repository)
    return RepositoryOrganizationService(
        organization_repository=organization_repository,
        user_repository=FakeUserRepository(organization_repository.users),
        authorization_service=_authorization(
            organization_repository, project_repository
        ),
        principal=principal,
    )


def _project_service(
    organization_repository: FakeOrganizationRepository,
    project_repository: FakeProjectRepository,
    *,
    principal: AuthenticatedPrincipal,
) -> RepositoryProjectService:
    return RepositoryProjectService(
        project_repository=project_repository,
        organization_repository=organization_repository,
        authorization_service=_authorization(
            organization_repository, project_repository
        ),
        principal=principal,
    )


def _authorization(
    organization_repository: FakeOrganizationRepository,
    project_repository: FakeProjectRepository,
) -> AuthorizationService:
    return AuthorizationService(
        organization_repository=organization_repository,
        project_repository=project_repository,
    )


def _principal(user_id: UUID) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=user_id,
        issuer="test",
        subject=str(user_id),
        email=f"{user_id}@example.test",
    )


def _user(user_id: UUID, *, is_active: bool = True) -> UserRecord:
    return UserRecord(
        id=user_id,
        issuer="test",
        external_subject=str(user_id),
        email=f"{user_id}@example.test",
        display_name=str(user_id),
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )


def _run(coro):
    import asyncio

    return asyncio.run(coro)
