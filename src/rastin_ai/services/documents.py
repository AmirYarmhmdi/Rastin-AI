"""File guide.

- Use: Coordinates document-facing API operations through upload persistence.
- Usage: Import DocumentService and StoredDocumentService from
  rastin_ai.services.documents.
- Duties: Defines stable document records for uploaded files and validation.
- Depends on: Project modules: rastin_ai.core.exceptions,
  rastin_ai.repositories.documents, rastin_ai.services.document_ingestion,
  and rastin_ai.services.upload.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePath
from typing import Protocol
from uuid import UUID

from fastapi import status

from rastin_ai.core.exceptions import AppException
from rastin_ai.observability import observed_workflow, safe_update_observation
from rastin_ai.repositories.documents import (
    DocumentRepository,
    UploadedDocumentRecord,
)
from rastin_ai.services.document_ingestion import DocumentIngestionService
from rastin_ai.services.upload import UploadInput, UploadService


class DocumentNotFoundError(AppException):
    """Raised when a requested document ID is not known."""

    def __init__(self, document_id: UUID) -> None:
        super().__init__(
            "Document not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="DOCUMENT_NOT_FOUND",
            details={"document_id": str(document_id)},
        )


class InvalidDocumentUploadError(AppException):
    """Raised when an upload request is structurally invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_DOCUMENT_UPLOAD",
        )


@dataclass(frozen=True)
class DocumentUpload:
    filename: str
    content: bytes
    content_type: str | None = None


@dataclass(frozen=True)
class DocumentRecord:
    document_id: UUID
    filename: str
    content_type: str | None
    status: str
    created_at: datetime
    workflow_id: UUID | None = None
    size_bytes: int = 0
    normalized_extension: str | None = None
    storage_key: str | None = None
    storage_backend: str | None = None
    checksum_sha256: str | None = None
    updated_at: datetime | None = None
    file_metadata_id: UUID | None = None
    file_storage_status: str | None = None
    indexing_error_code: str | None = None
    indexing_error_message: str | None = None


class DocumentService(Protocol):
    async def upload_document(self, upload: DocumentUpload) -> DocumentRecord:
        """Store a document upload and return its public document record."""

    async def list_documents(self) -> list[DocumentRecord]:
        """Return documents known to the application."""

    async def ensure_documents_exist(self, document_ids: list[UUID]) -> None:
        """Raise if any document ID is unknown."""

    async def get_documents(self, document_ids: list[UUID]) -> list[DocumentRecord]:
        """Return known document records in requested order, or raise."""


class StoredDocumentService:
    """Expose logical uploaded documents through the document API abstraction."""

    def __init__(
        self,
        *,
        upload_service: UploadService,
        document_repository: DocumentRepository,
        ingestion_service: DocumentIngestionService,
        user_id: UUID,
    ) -> None:
        self._upload_service = upload_service
        self._document_repository = document_repository
        self._ingestion_service = ingestion_service
        self._user_id = user_id

    async def upload_document(self, upload: DocumentUpload) -> DocumentRecord:
        filename = upload.filename.strip()
        if not filename:
            raise InvalidDocumentUploadError("Uploaded document filename is required.")

        with observed_workflow(
            name="document.upload_index",
            input={
                "extension": PurePath(filename).suffix.lower() or None,
                "content_type": upload.content_type,
                "size_bytes": len(upload.content),
            },
            metadata={
                "workflow_type": "document_upload_index",
                "content_type": upload.content_type,
                "size_bytes": len(upload.content),
            },
        ) as observation:
            record = await self._upload_service.upload(
                UploadInput(
                    original_filename=filename,
                    content=upload.content,
                    content_type=upload.content_type,
                )
            )
            indexed_record = await self._ingestion_service.index_uploaded_document(
                record
            )
            document_record = _document_record_from_uploaded_document(indexed_record)
            safe_update_observation(
                observation,
                output={
                    "document_id": str(document_record.document_id),
                    "file_metadata_id": (
                        str(document_record.file_metadata_id)
                        if document_record.file_metadata_id is not None
                        else None
                    ),
                    "status": document_record.status,
                    "indexing_error_code": document_record.indexing_error_code,
                },
            )
            return document_record

    async def list_documents(self) -> list[DocumentRecord]:
        records = await self._document_repository.list_uploaded_documents(
            user_id=self._user_id,
        )
        return [_document_record_from_uploaded_document(record) for record in records]

    async def ensure_documents_exist(self, document_ids: list[UUID]) -> None:
        await self.get_documents(document_ids)

    async def get_documents(self, document_ids: list[UUID]) -> list[DocumentRecord]:
        records = []
        seen: set[UUID] = set()
        for document_id in document_ids:
            if document_id in seen:
                continue
            seen.add(document_id)
            record = await self._document_repository.get_by_id(
                document_id,
                user_id=self._user_id,
            )
            if record is None:
                raise DocumentNotFoundError(document_id)
            records.append(_document_record_from_uploaded_document(record))

        return records


def _document_record_from_uploaded_document(
    record: UploadedDocumentRecord,
) -> DocumentRecord:
    return DocumentRecord(
        document_id=record.document_id,
        filename=record.filename,
        content_type=record.content_type,
        status=record.status,
        created_at=record.created_at,
        size_bytes=record.size_bytes,
        normalized_extension=record.normalized_extension,
        storage_key=record.storage_key,
        storage_backend=record.storage_backend,
        checksum_sha256=record.checksum_sha256,
        updated_at=record.updated_at,
        file_metadata_id=record.file_metadata_id,
        file_storage_status=record.file_storage_status,
        indexing_error_code=record.indexing_error_code,
        indexing_error_message=record.indexing_error_message,
    )
