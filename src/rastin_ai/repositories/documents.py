"""File guide.

- Use: Stores and reads logical documents with their uploaded file metadata.
- Usage: Import DocumentRepository and SQLAlchemyDocumentRepository from
  rastin_ai.repositories.documents.
- Duties: Creates linked session, document, and file metadata rows in one
  transaction and returns upload-ready document records.
- Depends on: Project modules: rastin_ai.database.enums and models.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rastin_ai.database.enums import (
    ConversationSessionStatus,
    DocumentStatus,
    FileStorageStatus,
)
from rastin_ai.database.models.conversation_session import ConversationSession
from rastin_ai.database.models.document import Document
from rastin_ai.database.models.file_metadata import FileMetadata


@dataclass(frozen=True)
class UploadedDocumentCreate:
    user_id: UUID
    document_id: UUID
    file_metadata_id: UUID
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
class UploadedDocumentRecord:
    user_id: UUID | None
    document_id: UUID
    session_id: UUID
    file_metadata_id: UUID
    filename: str
    content_type: str | None
    normalized_extension: str
    storage_key: str
    storage_backend: str
    size_bytes: int
    checksum_sha256: str
    status: str
    indexing_error_code: str | None
    indexing_error_message: str | None
    file_storage_status: str
    created_at: datetime
    updated_at: datetime


class DocumentRepository(Protocol):
    async def create_uploaded_document(
        self,
        document: UploadedDocumentCreate,
    ) -> UploadedDocumentRecord:
        """Persist one logical document and its uploaded file metadata."""

    async def get_by_id(
        self,
        document_id: UUID,
        *,
        user_id: UUID,
    ) -> UploadedDocumentRecord | None:
        """Return a logical document and file metadata by document ID."""

    async def list_uploaded_documents(
        self,
        *,
        user_id: UUID,
    ) -> list[UploadedDocumentRecord]:
        """Return uploaded documents with their file metadata."""

    async def update_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        *,
        user_id: UUID,
        indexing_error_code: str | None = None,
        indexing_error_message: str | None = None,
    ) -> UploadedDocumentRecord:
        """Update document lifecycle status and optional indexing failure details."""


class SQLAlchemyDocumentRepository:
    """SQLAlchemy-backed repository for logical documents."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_uploaded_document(
        self,
        document: UploadedDocumentCreate,
    ) -> UploadedDocumentRecord:
        conversation_session = ConversationSession(
            id=uuid4(),
            user_id=document.user_id,
            title=document.original_filename,
            status=ConversationSessionStatus.ACTIVE.value,
        )
        document_model = Document(
            id=document.document_id,
            session=conversation_session,
            user_id=document.user_id,
            name=document.original_filename,
            status=document.document_status.value,
        )
        file_metadata = FileMetadata(
            id=document.file_metadata_id,
            document=document_model,
            user_id=document.user_id,
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
            created_record = _to_uploaded_document_record(
                document_model,
                file_metadata,
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return created_record

    async def get_by_id(
        self,
        document_id: UUID,
        *,
        user_id: UUID,
    ) -> UploadedDocumentRecord | None:
        result = await self._session.execute(
            select(Document, FileMetadata)
            .join(FileMetadata, FileMetadata.document_id == Document.id)
            .where(Document.id == document_id, Document.user_id == user_id),
        )
        row = result.one_or_none()
        if row is None:
            return None

        document, file_metadata = row
        return _to_uploaded_document_record(document, file_metadata)

    async def list_uploaded_documents(
        self,
        *,
        user_id: UUID,
    ) -> list[UploadedDocumentRecord]:
        result = await self._session.execute(
            select(Document, FileMetadata)
            .join(FileMetadata, FileMetadata.document_id == Document.id)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc()),
        )
        return [
            _to_uploaded_document_record(document, file_metadata)
            for document, file_metadata in result.all()
        ]

    async def update_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        *,
        user_id: UUID,
        indexing_error_code: str | None = None,
        indexing_error_message: str | None = None,
    ) -> UploadedDocumentRecord:
        result = await self._session.execute(
            select(Document, FileMetadata)
            .join(FileMetadata, FileMetadata.document_id == Document.id)
            .where(Document.id == document_id, Document.user_id == user_id),
        )
        row = result.one_or_none()
        if row is None:
            msg = f"Document not found while updating status: {document_id}"
            raise LookupError(msg)

        document, file_metadata = row
        document.status = status.value
        document.indexing_error_code = indexing_error_code
        document.indexing_error_message = indexing_error_message

        try:
            await self._session.flush()
            await self._session.refresh(document)
            updated_record = _to_uploaded_document_record(document, file_metadata)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return updated_record


def _to_uploaded_document_record(
    document: Document,
    file_metadata: FileMetadata,
) -> UploadedDocumentRecord:
    return UploadedDocumentRecord(
        user_id=document.user_id,
        document_id=document.id,
        session_id=document.session_id,
        file_metadata_id=file_metadata.id,
        filename=file_metadata.original_filename,
        content_type=file_metadata.content_type,
        normalized_extension=file_metadata.normalized_extension,
        storage_key=file_metadata.storage_key,
        storage_backend=file_metadata.storage_backend,
        size_bytes=file_metadata.size_bytes,
        checksum_sha256=file_metadata.checksum_sha256 or "",
        status=document.status,
        indexing_error_code=document.indexing_error_code,
        indexing_error_message=document.indexing_error_message,
        file_storage_status=file_metadata.status,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
