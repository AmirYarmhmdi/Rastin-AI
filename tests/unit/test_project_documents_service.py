"""Unit tests for project-scoped document services."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from rastin_ai.database.enums import (
    DocumentScope,
    DocumentStatus,
    OrganizationMemberRole,
    ProjectMemberRole,
)
from rastin_ai.repositories.organizations import (
    OrganizationMemberRecord,
    OrganizationRecord,
)
from rastin_ai.repositories.project_documents import (
    ChatAttachmentCreate,
    ProjectDocumentCreate,
    ProjectDocumentRecord,
)
from rastin_ai.repositories.projects import ProjectRecord
from rastin_ai.security.auth import AuthenticatedPrincipal
from rastin_ai.services.authorization import (
    AuthorizationForbiddenError,
    AuthorizationService,
    ProjectAccessContext,
)
from rastin_ai.services.project_documents import (
    ProjectDocumentUpload,
    StoredProjectDocumentService,
)
from rastin_ai.storage.base import StoredObject

ORGANIZATION_ID = UUID("11111111-1111-4111-8111-111111111111")
PROJECT_ID = UUID("22222222-2222-4222-8222-222222222222")
DOCUMENT_ID = UUID("55555555-5555-4555-8555-555555555555")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


class FakeStorageProvider:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def save(self, storage_key: str, content: bytes) -> StoredObject:
        self.objects[storage_key] = content
        return StoredObject(storage_key=storage_key, size_bytes=len(content))

    def open(self, storage_key: str) -> bytes:
        return self.objects[storage_key]

    def read(self, storage_key: str) -> bytes:
        return self.open(storage_key)

    def delete(self, storage_key: str) -> None:
        self.deleted.append(storage_key)
        self.objects.pop(storage_key, None)

    def exists(self, storage_key: str) -> bool:
        return storage_key in self.objects


class FakeProjectDocumentRepository:
    def __init__(self) -> None:
        self.created: list[ProjectDocumentCreate] = []
        self.records: dict[UUID, ProjectDocumentRecord] = {}
        self.deleted: list[UUID] = []

    async def create_project_library_document(
        self,
        document: ProjectDocumentCreate,
    ) -> ProjectDocumentRecord:
        self.created.append(document)
        record = _record_from_create(document)
        self.records[record.document_id] = record
        return record

    async def create_chat_attachment_document(
        self,
        document: ChatAttachmentCreate,
    ) -> ProjectDocumentRecord:
        self.created.append(document)
        record = _record_from_create(
            document,
            document_scope=DocumentScope.CHAT_ATTACHMENT,
            session_id=document.session_id,
        )
        self.records[record.document_id] = record
        return record

    async def list_project_library_documents(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> list[ProjectDocumentRecord]:
        return [
            record
            for record in self.records.values()
            if record.organization_id == organization_id
            and record.project_id == project_id
            and record.document_scope == DocumentScope.PROJECT_LIBRARY.value
        ]

    async def get_project_library_document(
        self,
        document_id: UUID,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> ProjectDocumentRecord | None:
        record = self.records.get(document_id)
        if (
            record is None
            or record.organization_id != organization_id
            or record.project_id != project_id
            or record.document_scope != DocumentScope.PROJECT_LIBRARY.value
        ):
            return None
        return record

    async def update_status(
        self,
        document_id: UUID,
        *,
        organization_id: UUID,
        project_id: UUID,
        document_scope: DocumentScope,
        status: DocumentStatus,
        indexing_error_code: str | None = None,
        indexing_error_message: str | None = None,
    ) -> ProjectDocumentRecord:
        record = self.records.get(document_id)
        assert record is not None
        assert record.organization_id == organization_id
        assert record.project_id == project_id
        assert record.document_scope == document_scope.value
        updated = replace(
            record,
            status=status.value,
            indexing_error_code=indexing_error_code,
            indexing_error_message=indexing_error_message,
        )
        self.records[document_id] = updated
        return updated

    async def delete_project_library_document(
        self,
        document_id: UUID,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> bool:
        record = await self.get_project_library_document(
            document_id,
            organization_id=organization_id,
            project_id=project_id,
        )
        if record is None:
            return False
        self.deleted.append(document_id)
        self.records.pop(document_id, None)
        return True


class FakeAuthorizationService(AuthorizationService):
    def __init__(self) -> None:
        pass


class FakeVectorStore:
    def __init__(self) -> None:
        self.deletes: list[dict[str, object]] = []

    def delete(self, **kwargs: object) -> None:
        self.deletes.append(kwargs)


class FakeIndexer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def index(self, path, **kwargs: object) -> None:
        self.calls.append({"path": path, **kwargs})


def test_project_library_upload_uses_project_scope_and_null_session() -> None:
    storage = FakeStorageProvider()
    repository = FakeProjectDocumentRepository()
    indexer = FakeIndexer()
    service = _service(storage=storage, repository=repository, indexer=indexer)

    record = asyncio.run(
        service.upload_project_library_document(
            _context(),
            ProjectDocumentUpload(
                filename=" Notes.TXT ",
                content=b"alpha",
                content_type="text/plain",
            ),
        )
    )

    created = repository.created[0]
    assert created.organization_id == ORGANIZATION_ID
    assert created.project_id == PROJECT_ID
    assert record.document_scope == DocumentScope.PROJECT_LIBRARY.value
    assert record.session_id is None
    assert record.status == DocumentStatus.INDEXED.value
    assert record.storage_key.startswith(
        f"organizations/{ORGANIZATION_ID}/projects/{PROJECT_ID}/library/documents/"
    )
    assert indexer.calls[0]["metadata"]["document_scope"] == "PROJECT_LIBRARY"
    assert indexer.calls[0]["metadata"]["organization_id"] == str(ORGANIZATION_ID)
    assert indexer.calls[0]["metadata"]["project_id"] == str(PROJECT_ID)


def test_chat_attachment_upload_uses_same_document_id_everywhere() -> None:
    storage = FakeStorageProvider()
    repository = FakeProjectDocumentRepository()
    indexer = FakeIndexer()
    service = _service(storage=storage, repository=repository, indexer=indexer)
    session_id = UUID("99999999-9999-4999-8999-999999999999")

    record = asyncio.run(
        service.upload_chat_attachment_document(
            _context(),
            session_id,
            ProjectDocumentUpload(
                filename=" Chat.TXT ",
                content=b"chat alpha",
                content_type="text/plain",
            ),
        )
    )

    created = repository.created[0]
    expected_key = (
        f"organizations/{ORGANIZATION_ID}/projects/{PROJECT_ID}/"
        f"sessions/{session_id}/attachments/{DOCUMENT_ID}/source/content.txt"
    )
    assert created.document_id == DOCUMENT_ID
    assert created.file_metadata_id == DOCUMENT_ID
    assert created.storage_key == expected_key
    assert record.document_id == DOCUMENT_ID
    assert record.document_scope == DocumentScope.CHAT_ATTACHMENT.value
    assert record.session_id == session_id
    assert expected_key in storage.objects
    assert indexer.calls[0]["document_id"] == str(DOCUMENT_ID)
    assert indexer.calls[0]["metadata"]["document_scope"] == "CHAT_ATTACHMENT"
    assert indexer.calls[0]["metadata"]["session_id"] == str(session_id)
    assert indexer.calls[0]["metadata"]["storage_key"] == expected_key


def test_viewer_cannot_upload_project_library_document() -> None:
    service = _service()

    with pytest.raises(AuthorizationForbiddenError):
        asyncio.run(
            service.upload_project_library_document(
                _context(role=ProjectMemberRole.VIEWER),
                ProjectDocumentUpload(
                    filename="notes.txt",
                    content=b"alpha",
                    content_type="text/plain",
                ),
            )
        )


def test_project_library_delete_uses_project_scoped_vector_filter() -> None:
    storage = FakeStorageProvider()
    repository = FakeProjectDocumentRepository()
    vector_store = FakeVectorStore()
    service = _service(
        storage=storage,
        repository=repository,
        vector_store=vector_store,
    )
    storage.save("project-key", b"alpha")
    repository.records[DOCUMENT_ID] = _project_document_record(
        storage_key="project-key",
    )

    asyncio.run(service.delete_project_library_document(_context(), DOCUMENT_ID))

    assert vector_store.deletes == [
        {
            "document_id": str(DOCUMENT_ID),
            "filters": {
                "organization_id": str(ORGANIZATION_ID),
                "project_id": str(PROJECT_ID),
                "document_scope": "PROJECT_LIBRARY",
            },
        }
    ]
    assert storage.deleted == ["project-key"]
    assert repository.deleted == [DOCUMENT_ID]


def _service(
    *,
    storage: FakeStorageProvider | None = None,
    repository: FakeProjectDocumentRepository | None = None,
    vector_store: FakeVectorStore | None = None,
    indexer: FakeIndexer | None = None,
) -> StoredProjectDocumentService:
    storage = storage or FakeStorageProvider()
    repository = repository or FakeProjectDocumentRepository()
    vector_store = vector_store or FakeVectorStore()
    indexer = indexer or FakeIndexer()
    return StoredProjectDocumentService(
        storage_provider=storage,
        project_document_repository=repository,
        authorization_service=FakeAuthorizationService(),
        vector_store_factory=lambda: vector_store,
        indexer_factory=lambda _loader: indexer,
        storage_backend="local",
        file_id_factory=lambda: DOCUMENT_ID,
    )


def _context(
    *,
    role: ProjectMemberRole = ProjectMemberRole.ADMIN,
) -> ProjectAccessContext:
    return ProjectAccessContext(
        principal=AuthenticatedPrincipal(
            user_id=USER_ID,
            issuer="test",
            subject=str(USER_ID),
            email="user@example.test",
        ),
        organization=OrganizationRecord(
            id=ORGANIZATION_ID,
            name="Acme",
            slug="acme",
            created_by_user_id=USER_ID,
            created_at=NOW,
            updated_at=NOW,
        ),
        project=ProjectRecord(
            id=PROJECT_ID,
            organization_id=ORGANIZATION_ID,
            name="Apollo",
            description=None,
            created_by_user_id=USER_ID,
            created_at=NOW,
            updated_at=NOW,
        ),
        organization_membership=OrganizationMemberRecord(
            id=UUID("33333333-3333-4333-8333-333333333333"),
            organization_id=ORGANIZATION_ID,
            user_id=USER_ID,
            role=OrganizationMemberRole.MEMBER.value,
            user_is_active=True,
            user_email="user@example.test",
            user_display_name="User",
            created_at=NOW,
            updated_at=NOW,
        ),
        project_membership=None,
        effective_project_role=role.value,
    )


def _record_from_create(
    document: ProjectDocumentCreate | ChatAttachmentCreate,
    *,
    document_scope: DocumentScope = DocumentScope.PROJECT_LIBRARY,
    session_id: UUID | None = None,
) -> ProjectDocumentRecord:
    return _project_document_record(
        document_id=document.document_id,
        file_metadata_id=document.file_metadata_id,
        storage_key=document.storage_key,
        filename=document.original_filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        checksum_sha256=document.checksum_sha256,
        document_scope=document_scope,
        session_id=session_id,
    )


def _project_document_record(
    *,
    document_id: UUID = DOCUMENT_ID,
    file_metadata_id: UUID = DOCUMENT_ID,
    storage_key: str = "project-key",
    filename: str = "notes.txt",
    content_type: str | None = "text/plain",
    size_bytes: int = 5,
    checksum_sha256: str = "checksum",
    document_scope: DocumentScope = DocumentScope.PROJECT_LIBRARY,
    session_id: UUID | None = None,
) -> ProjectDocumentRecord:
    return ProjectDocumentRecord(
        document_id=document_id,
        file_metadata_id=file_metadata_id,
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        uploaded_by_user_id=USER_ID,
        filename=filename,
        content_type=content_type,
        normalized_extension=".txt",
        storage_key=storage_key,
        storage_backend="local",
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256,
        document_scope=document_scope.value,
        session_id=session_id,
        status=DocumentStatus.UPLOADED.value,
        indexing_error_code=None,
        indexing_error_message=None,
        file_storage_status="stored",
        created_at=NOW,
        updated_at=NOW,
    )
