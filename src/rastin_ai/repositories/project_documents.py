"""Repositories for project-scoped documents and file metadata."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rastin_ai.database.enums import (
    DocumentScope,
    DocumentStatus,
    FileStorageStatus,
)
from rastin_ai.database.models.conversation_session import ConversationSession
from rastin_ai.database.models.document import Document
from rastin_ai.database.models.file_metadata import FileMetadata
from rastin_ai.repositories.organizations import RepositoryConflictError


@dataclass(frozen=True)
class ProjectDocumentCreate:
    document_id: UUID
    file_metadata_id: UUID
    organization_id: UUID
    project_id: UUID
    uploaded_by_user_id: UUID
    original_filename: str
    storage_key: str
    storage_backend: str
    content_type: str | None
    normalized_extension: str
    size_bytes: int
    checksum_sha256: str
    document_status: DocumentStatus = DocumentStatus.UPLOADED
    file_storage_status: FileStorageStatus = FileStorageStatus.STORED


@dataclass(frozen=True)
class ChatAttachmentCreate:
    document_id: UUID
    file_metadata_id: UUID
    organization_id: UUID
    project_id: UUID
    uploaded_by_user_id: UUID
    session_id: UUID
    original_filename: str
    storage_key: str
    storage_backend: str
    content_type: str | None
    normalized_extension: str
    size_bytes: int
    checksum_sha256: str
    document_status: DocumentStatus = DocumentStatus.UPLOADED
    file_storage_status: FileStorageStatus = FileStorageStatus.STORED


@dataclass(frozen=True)
class ProjectDocumentRecord:
    document_id: UUID
    file_metadata_id: UUID
    organization_id: UUID
    project_id: UUID
    uploaded_by_user_id: UUID | None
    filename: str
    content_type: str | None
    normalized_extension: str
    storage_key: str
    storage_backend: str
    size_bytes: int
    checksum_sha256: str
    document_scope: str
    session_id: UUID | None
    status: str
    indexing_error_code: str | None
    indexing_error_message: str | None
    file_storage_status: str
    created_at: datetime
    updated_at: datetime


class ProjectDocumentRepository(Protocol):
    async def create_project_library_document(
        self,
        document: ProjectDocumentCreate,
    ) -> ProjectDocumentRecord:
        """Persist one project-library document and its file metadata."""

    async def create_chat_attachment_document(
        self,
        document: ChatAttachmentCreate,
    ) -> ProjectDocumentRecord:
        """Persist a chat-only attachment for a project-scoped session."""

    async def list_project_library_documents(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> list[ProjectDocumentRecord]:
        """List project-library documents within one project."""

    async def get_project_library_document(
        self,
        document_id: UUID,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> ProjectDocumentRecord | None:
        """Return a project-library document through scoped metadata join."""

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
        """Update a project-scoped document lifecycle status."""

    async def delete_project_library_document(
        self,
        document_id: UUID,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> bool:
        """Delete one project-library document and its file metadata."""


class SQLAlchemyProjectDocumentRepository:
    """SQLAlchemy-backed project document repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_project_library_document(
        self,
        document: ProjectDocumentCreate,
    ) -> ProjectDocumentRecord:
        return await self._create_document(
            document,
            document_scope=DocumentScope.PROJECT_LIBRARY,
            session_id=None,
        )

    async def create_chat_attachment_document(
        self,
        document: ChatAttachmentCreate,
    ) -> ProjectDocumentRecord:
        session = await self._get_project_session(
            document.session_id,
            organization_id=document.organization_id,
            project_id=document.project_id,
        )
        if session is None:
            msg = "Project conversation session not found for chat attachment."
            raise LookupError(msg)

        return await self._create_document(
            document,
            document_scope=DocumentScope.CHAT_ATTACHMENT,
            session_id=document.session_id,
        )

    async def list_project_library_documents(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> list[ProjectDocumentRecord]:
        result = await self._session.execute(
            _project_document_select()
            .where(
                Document.organization_id == organization_id,
                Document.project_id == project_id,
                Document.document_scope == DocumentScope.PROJECT_LIBRARY.value,
            )
            .order_by(Document.created_at.desc())
        )
        return [
            _to_project_document_record(document, metadata)
            for document, metadata in result.all()
        ]

    async def get_project_library_document(
        self,
        document_id: UUID,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> ProjectDocumentRecord | None:
        result = await self._session.execute(
            _project_document_select().where(
                Document.id == document_id,
                Document.organization_id == organization_id,
                Document.project_id == project_id,
                Document.document_scope == DocumentScope.PROJECT_LIBRARY.value,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        document, metadata = row
        return _to_project_document_record(document, metadata)

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
        result = await self._session.execute(
            _project_document_select().where(
                Document.id == document_id,
                Document.organization_id == organization_id,
                Document.project_id == project_id,
                Document.document_scope == document_scope.value,
            )
        )
        row = result.one_or_none()
        if row is None:
            msg = f"Project document not found while updating status: {document_id}"
            raise LookupError(msg)

        document, metadata = row
        document.status = status.value
        document.indexing_error_code = indexing_error_code
        document.indexing_error_message = indexing_error_message

        try:
            await self._session.flush()
            await self._session.refresh(document)
            updated = _to_project_document_record(document, metadata)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return updated

    async def delete_project_library_document(
        self,
        document_id: UUID,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> bool:
        result = await self._session.execute(
            select(Document, FileMetadata)
            .join(FileMetadata, FileMetadata.document_id == Document.id)
            .where(
                Document.id == document_id,
                Document.organization_id == organization_id,
                Document.project_id == project_id,
                Document.document_scope == DocumentScope.PROJECT_LIBRARY.value,
            )
        )
        row = result.one_or_none()
        if row is None:
            return False

        document, metadata = row
        try:
            await self._session.delete(metadata)
            await self._session.delete(document)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return True

    async def _create_document(
        self,
        document: ProjectDocumentCreate,
        *,
        document_scope: DocumentScope,
        session_id: UUID | None,
    ) -> ProjectDocumentRecord:
        document_model = Document(
            id=document.document_id,
            session_id=session_id,
            user_id=document.uploaded_by_user_id,
            organization_id=document.organization_id,
            project_id=document.project_id,
            document_scope=document_scope.value,
            name=document.original_filename,
            status=document.document_status.value,
        )
        file_metadata = FileMetadata(
            id=document.file_metadata_id,
            document=document_model,
            user_id=document.uploaded_by_user_id,
            original_filename=document.original_filename,
            storage_key=document.storage_key,
            storage_backend=document.storage_backend,
            content_type=document.content_type,
            normalized_extension=document.normalized_extension,
            size_bytes=document.size_bytes,
            status=document.file_storage_status.value,
            checksum_sha256=document.checksum_sha256,
        )
        self._session.add(file_metadata)

        try:
            await self._session.flush()
            await self._session.refresh(document_model)
            await self._session.refresh(file_metadata)
            created = _to_project_document_record(document_model, file_metadata)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise RepositoryConflictError("Project document already exists.") from exc
        except Exception:
            await self._session.rollback()
            raise

        return created

    async def _get_project_session(
        self,
        session_id: UUID,
        *,
        organization_id: UUID,
        project_id: UUID,
    ) -> ConversationSession | None:
        result = await self._session.execute(
            select(ConversationSession).where(
                ConversationSession.id == session_id,
                ConversationSession.organization_id == organization_id,
                ConversationSession.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()


def _project_document_select():
    return select(Document, FileMetadata).join(
        FileMetadata,
        FileMetadata.document_id == Document.id,
    )


def _to_project_document_record(
    document: Document,
    metadata: FileMetadata,
) -> ProjectDocumentRecord:
    if document.organization_id is None or document.project_id is None:
        msg = f"Document is missing project scope: {document.id}"
        raise LookupError(msg)

    return ProjectDocumentRecord(
        document_id=document.id,
        file_metadata_id=metadata.id,
        organization_id=document.organization_id,
        project_id=document.project_id,
        uploaded_by_user_id=document.user_id,
        filename=metadata.original_filename,
        content_type=metadata.content_type,
        normalized_extension=metadata.normalized_extension,
        storage_key=metadata.storage_key,
        storage_backend=metadata.storage_backend,
        size_bytes=metadata.size_bytes,
        checksum_sha256=metadata.checksum_sha256 or "",
        document_scope=document.document_scope,
        session_id=document.session_id,
        status=document.status,
        indexing_error_code=document.indexing_error_code,
        indexing_error_message=document.indexing_error_message,
        file_storage_status=metadata.status,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
