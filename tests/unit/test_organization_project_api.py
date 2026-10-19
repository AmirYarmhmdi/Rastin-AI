"""API tests for organization/project foundation endpoints."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from helpers import create_isolated_app

from rastin_ai.database.enums import OrganizationMemberRole, ProjectMemberRole
from rastin_ai.repositories.organizations import (
    OrganizationMemberRecord,
    OrganizationRecord,
)
from rastin_ai.repositories.project_documents import ProjectDocumentRecord
from rastin_ai.repositories.projects import ProjectMemberRecord, ProjectRecord
from rastin_ai.security.auth import AuthenticatedPrincipal
from rastin_ai.services.authorization import (
    OrganizationAccessContext,
    ProjectAccessContext,
    ProjectNotFoundError,
)
from rastin_ai.services.organizations import (
    OrganizationInput,
    OrganizationMemberInput,
)
from rastin_ai.services.project_documents import ProjectDocumentUpload
from rastin_ai.services.projects import ProjectInput, ProjectMemberInput, ProjectView

ORGANIZATION_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = UUID("22222222-2222-4222-8222-222222222222")
DOCUMENT_ID = UUID("55555555-5555-4555-8555-555555555555")
OWNER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
MEMBER_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


class FakeOrganizationService:
    def __init__(self) -> None:
        self.created_organizations: list[OrganizationInput] = []
        self.added_members: list[OrganizationMemberInput] = []

    async def create_organization(
        self,
        organization: OrganizationInput,
    ) -> OrganizationRecord:
        self.created_organizations.append(organization)
        return _organization()

    async def list_organizations(self) -> list[OrganizationRecord]:
        return [_organization()]

    async def list_members(
        self,
        context: OrganizationAccessContext,
    ) -> list[OrganizationMemberRecord]:
        _ = context
        return [_organization_member()]

    async def add_member(
        self,
        context: OrganizationAccessContext,
        member: OrganizationMemberInput,
    ) -> OrganizationMemberRecord:
        _ = context
        self.added_members.append(member)
        return _organization_member(user_id=member.user_id, role=member.role)


class FakeProjectService:
    def __init__(self) -> None:
        self.created_projects: list[ProjectInput] = []
        self.added_members: list[ProjectMemberInput] = []
        self.removed_members: list[UUID] = []

    async def list_projects(
        self,
        context: OrganizationAccessContext,
    ) -> list[ProjectView]:
        _ = context
        return [_project_view()]

    async def create_project(
        self,
        context: OrganizationAccessContext,
        project: ProjectInput,
    ) -> ProjectView:
        _ = context
        self.created_projects.append(project)
        return _project_view(description=project.description)

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
        _ = context
        return [_project_member()]

    async def add_member(
        self,
        context: ProjectAccessContext,
        member: ProjectMemberInput,
    ) -> ProjectMemberRecord:
        _ = context
        self.added_members.append(member)
        return _project_member(user_id=member.user_id, role=member.role)

    async def remove_member(
        self,
        context: ProjectAccessContext,
        user_id: UUID,
    ) -> None:
        _ = context
        self.removed_members.append(user_id)


class FakeProjectDocumentService:
    def __init__(self) -> None:
        self.uploads: list[ProjectDocumentUpload] = []
        self.deleted_document_ids: list[UUID] = []

    async def upload_project_library_document(
        self,
        context: ProjectAccessContext,
        upload: ProjectDocumentUpload,
    ) -> ProjectDocumentRecord:
        _ = context
        self.uploads.append(upload)
        return _project_document(
            filename=upload.filename,
            content_type=upload.content_type,
        )

    async def list_project_library_documents(
        self,
        context: ProjectAccessContext,
    ) -> list[ProjectDocumentRecord]:
        _ = context
        return [_project_document()]

    async def get_project_library_document(
        self,
        context: ProjectAccessContext,
        document_id: UUID,
    ) -> ProjectDocumentRecord:
        _ = context
        return _project_document(document_id=document_id)

    async def read_project_library_document(
        self,
        context: ProjectAccessContext,
        document_id: UUID,
    ) -> tuple[ProjectDocumentRecord, bytes]:
        _ = context
        return _project_document(document_id=document_id), b"project content"

    async def delete_project_library_document(
        self,
        context: ProjectAccessContext,
        document_id: UUID,
    ) -> None:
        _ = context
        self.deleted_document_ids.append(document_id)


def test_create_and_list_organizations(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)
    service = FakeOrganizationService()

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_organization_service] = lambda: service

    with TestClient(app) as client:
        create_response = client.post(
            "/api/v1/organizations",
            json={"name": "Acme Labs", "slug": "acme"},
        )
        list_response = client.get("/api/v1/organizations")

    assert create_response.status_code == 201
    assert create_response.json()["id"] == str(ORGANIZATION_ID)
    assert service.created_organizations == [
        OrganizationInput(name="Acme Labs", slug="acme")
    ]
    assert list_response.status_code == 200
    assert list_response.json()["organizations"][0]["slug"] == "acme"


def test_organization_member_routes_require_user_id(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)
    service = FakeOrganizationService()

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_organization_service] = lambda: service
    app.dependency_overrides[dependencies.get_organization_access_context] = (
        _organization_context
    )

    with TestClient(app) as client:
        invalid_response = client.post(
            f"/api/v1/organizations/{ORGANIZATION_ID}/members",
            json={"email": "member@example.test", "role": "MEMBER"},
        )
        valid_response = client.post(
            f"/api/v1/organizations/{ORGANIZATION_ID}/members",
            json={"user_id": str(MEMBER_ID), "role": "MEMBER"},
        )

    assert invalid_response.status_code == 422
    assert valid_response.status_code == 201
    assert service.added_members == [
        OrganizationMemberInput(
            user_id=MEMBER_ID,
            role=OrganizationMemberRole.MEMBER,
        )
    ]


def test_project_routes_expose_metadata_and_memberships(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)
    service = FakeProjectService()

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_project_service] = lambda: service
    app.dependency_overrides[dependencies.get_organization_access_context] = (
        _organization_context
    )
    app.dependency_overrides[dependencies.get_project_access_context] = _project_context

    with TestClient(app) as client:
        list_response = client.get(f"/api/v1/organizations/{ORGANIZATION_ID}/projects")
        create_response = client.post(
            f"/api/v1/organizations/{ORGANIZATION_ID}/projects",
            json={"name": "Apollo", "description": "Launch plan"},
        )
        detail_response = client.get(f"/api/v1/projects/{PROJECT_ID}")
        members_response = client.get(f"/api/v1/projects/{PROJECT_ID}/members")
        add_member_response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/members",
            json={"user_id": str(MEMBER_ID), "role": "VIEWER"},
        )
        delete_response = client.delete(
            f"/api/v1/projects/{PROJECT_ID}/members/{MEMBER_ID}"
        )

    assert list_response.status_code == 200
    assert list_response.json()["projects"][0]["effective_role"] == "ADMIN"
    assert create_response.status_code == 201
    assert service.created_projects == [
        ProjectInput(name="Apollo", description="Launch plan")
    ]
    assert detail_response.status_code == 200
    assert members_response.status_code == 200
    assert add_member_response.status_code == 201
    assert service.added_members == [
        ProjectMemberInput(user_id=MEMBER_ID, role=ProjectMemberRole.VIEWER)
    ]
    assert delete_response.status_code == 204
    assert service.removed_members == [MEMBER_ID]


def test_project_member_endpoint_rejects_non_project_role(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_project_service] = (
        lambda: FakeProjectService()
    )
    app.dependency_overrides[dependencies.get_project_access_context] = _project_context

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/members",
            json={"user_id": str(MEMBER_ID), "role": "OWNER"},
        )

    assert response.status_code == 422


def test_project_library_document_routes(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)
    service = FakeProjectDocumentService()

    from rastin_ai.api import dependencies

    app.dependency_overrides[dependencies.get_project_document_service] = (
        lambda: service
    )
    app.dependency_overrides[dependencies.get_project_access_context] = _project_context

    with TestClient(app) as client:
        upload_response = client.post(
            f"/api/v1/projects/{PROJECT_ID}/library/documents",
            files={"file": ("plans.txt", b"launch", "text/plain")},
        )
        list_response = client.get(f"/api/v1/projects/{PROJECT_ID}/library/documents")
        detail_response = client.get(
            f"/api/v1/projects/{PROJECT_ID}/library/documents/{DOCUMENT_ID}"
        )
        download_response = client.get(
            f"/api/v1/projects/{PROJECT_ID}/library/documents/{DOCUMENT_ID}/download"
        )
        delete_response = client.delete(
            f"/api/v1/projects/{PROJECT_ID}/library/documents/{DOCUMENT_ID}"
        )

    assert upload_response.status_code == 201
    assert upload_response.json()["document_scope"] == "PROJECT_LIBRARY"
    assert service.uploads == [
        ProjectDocumentUpload(
            filename="plans.txt",
            content=b"launch",
            content_type="text/plain",
        )
    ]
    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert download_response.status_code == 200
    assert download_response.content == b"project content"
    assert delete_response.status_code == 204
    assert service.deleted_document_ids == [DOCUMENT_ID]


def test_project_access_failure_is_non_disclosing(monkeypatch) -> None:
    app = create_isolated_app(monkeypatch)

    from rastin_ai.api import dependencies

    async def inaccessible_project_context(project_id: UUID) -> ProjectAccessContext:
        _ = project_id
        raise ProjectNotFoundError(PROJECT_ID)

    app.dependency_overrides[dependencies.get_project_access_context] = (
        inaccessible_project_context
    )
    app.dependency_overrides[dependencies.get_project_service] = (
        lambda: FakeProjectService()
    )

    with TestClient(app) as client:
        response = client.get(f"/api/v1/projects/{PROJECT_ID}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def _organization_context() -> OrganizationAccessContext:
    return OrganizationAccessContext(
        principal=_principal(),
        organization=_organization(),
        organization_membership=_organization_member(role=OrganizationMemberRole.OWNER),
    )


def _project_context() -> ProjectAccessContext:
    return ProjectAccessContext(
        principal=_principal(),
        organization=_organization(),
        project=_project(),
        organization_membership=_organization_member(role=OrganizationMemberRole.OWNER),
        project_membership=None,
        effective_project_role=ProjectMemberRole.ADMIN.value,
    )


def _project_view(description: str | None = None) -> ProjectView:
    return ProjectView(
        project=_project(description=description),
        effective_role=ProjectMemberRole.ADMIN.value,
        permissions=("projects.read", "projects.manage_members"),
    )


def _organization() -> OrganizationRecord:
    return OrganizationRecord(
        id=ORGANIZATION_ID,
        name="Acme Labs",
        slug="acme",
        created_by_user_id=OWNER_ID,
        created_at=NOW,
        updated_at=NOW,
    )


def _project(description: str | None = None) -> ProjectRecord:
    return ProjectRecord(
        id=PROJECT_ID,
        organization_id=ORGANIZATION_ID,
        name="Apollo",
        description=description,
        created_by_user_id=OWNER_ID,
        created_at=NOW,
        updated_at=NOW,
    )


def _organization_member(
    *,
    user_id: UUID = OWNER_ID,
    role: OrganizationMemberRole = OrganizationMemberRole.MEMBER,
) -> OrganizationMemberRecord:
    return OrganizationMemberRecord(
        id=UUID("33333333-3333-4333-8333-333333333333"),
        organization_id=ORGANIZATION_ID,
        user_id=user_id,
        role=role.value,
        user_is_active=True,
        user_email=f"{user_id}@example.test",
        user_display_name=str(user_id),
        created_at=NOW,
        updated_at=NOW,
    )


def _project_member(
    *,
    user_id: UUID = MEMBER_ID,
    role: ProjectMemberRole = ProjectMemberRole.MEMBER,
) -> ProjectMemberRecord:
    return ProjectMemberRecord(
        id=UUID("44444444-4444-4444-8444-444444444444"),
        project_id=PROJECT_ID,
        user_id=user_id,
        role=role.value,
        user_is_active=True,
        user_email=f"{user_id}@example.test",
        user_display_name=str(user_id),
        created_at=NOW,
        updated_at=NOW,
    )


def _project_document(
    *,
    document_id: UUID = DOCUMENT_ID,
    filename: str = "plans.txt",
    content_type: str | None = "text/plain",
) -> ProjectDocumentRecord:
    return ProjectDocumentRecord(
        document_id=document_id,
        file_metadata_id=document_id,
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        uploaded_by_user_id=OWNER_ID,
        filename=filename,
        content_type=content_type,
        normalized_extension=".txt",
        storage_key=(
            f"organizations/{ORGANIZATION_ID}/projects/{PROJECT_ID}/"
            f"library/documents/{document_id}/source/content.txt"
        ),
        storage_backend="local",
        size_bytes=7,
        checksum_sha256="checksum",
        document_scope="PROJECT_LIBRARY",
        session_id=None,
        status="indexed",
        indexing_error_code=None,
        indexing_error_message=None,
        file_storage_status="stored",
        created_at=NOW,
        updated_at=NOW,
    )


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=OWNER_ID,
        issuer="test",
        subject=str(OWNER_ID),
        email="owner@example.test",
    )
