"""File guide.

- Use: Coordinates file upload validation, storage, and metadata persistence.
- Usage: Import UnsupportedUploadFileTypeError, UploadInput, and UploadService from
  rastin_ai.services.upload.
- Duties: Defines UnsupportedUploadFileTypeError, UploadInput, and UploadService and
  related helper logic.
- Depends on: Project modules: rastin_ai.core.exceptions,
  rastin_ai.database.enums, rastin_ai.repositories.documents, and
  rastin_ai.storage.base.
"""

import hashlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePath
from uuid import UUID

from fastapi import status

from rastin_ai.core.exceptions import AppException
from rastin_ai.database.enums import DocumentStatus, FileStorageStatus
from rastin_ai.observability import observed_span, safe_update_observation
from rastin_ai.repositories.documents import (
    DocumentRepository,
    UploadedDocumentCreate,
    UploadedDocumentRecord,
)
from rastin_ai.storage.base import StorageProvider

logger = logging.getLogger(__name__)

SUPPORTED_UPLOAD_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".csv",
        ".xlsx",
        ".docx",
        ".json",
        ".txt",
        ".md",
    },
)


class UnsupportedUploadFileTypeError(AppException):
    """Raised when an uploaded file extension is not supported."""

    def __init__(self, filename: str, extension: str | None) -> None:
        details = {
            "filename": filename,
            "extension": extension,
            "supported_extensions": sorted(SUPPORTED_UPLOAD_EXTENSIONS),
        }
        super().__init__(
            "Unsupported upload file type.",
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="UNSUPPORTED_UPLOAD_FILE_TYPE",
            details=details,
        )


class UploadTooLargeError(AppException):
    """Raised when an uploaded file exceeds the configured size limit."""

    def __init__(self, filename: str, size_bytes: int, max_upload_bytes: int) -> None:
        super().__init__(
            "Uploaded file exceeds the configured size limit.",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            error_code="UPLOAD_TOO_LARGE",
            details={
                "filename": filename,
                "size_bytes": size_bytes,
                "max_upload_bytes": max_upload_bytes,
            },
        )


@dataclass(frozen=True)
class UploadInput:
    original_filename: str
    content: bytes
    content_type: str | None = None


class UploadService:
    """Coordinate file upload storage and metadata persistence."""

    def __init__(
        self,
        storage_provider: StorageProvider,
        document_repository: DocumentRepository,
        *,
        user_id: UUID,
        file_id_factory: Callable[[], uuid.UUID] = uuid.uuid4,
        storage_backend: str = "local",
        max_upload_bytes: int | None = None,
    ) -> None:
        self._storage_provider = storage_provider
        self._document_repository = document_repository
        self._user_id = user_id
        self._file_id_factory = file_id_factory
        self._storage_backend = storage_backend
        self._max_upload_bytes = max_upload_bytes

    async def upload(self, upload_input: UploadInput) -> UploadedDocumentRecord:
        normalized_extension = self._validate_extension(
            upload_input.original_filename,
        )
        self._validate_size(
            upload_input.original_filename,
            len(upload_input.content),
        )
        file_id = self._file_id_factory()
        storage_key = self._build_storage_key(file_id, normalized_extension)
        checksum_sha256 = hashlib.sha256(upload_input.content).hexdigest()

        stored_storage_key: str | None = None
        try:
            with observed_span(
                name="document.storage.write",
                input={
                    "extension": normalized_extension,
                    "content_type": upload_input.content_type,
                    "size_bytes": len(upload_input.content),
                    "storage_backend": self._storage_backend,
                },
            ) as observation:
                stored_object = self._storage_provider.save(
                    storage_key,
                    upload_input.content,
                )
                safe_update_observation(
                    observation,
                    output={
                        "status": "stored",
                        "size_bytes": stored_object.size_bytes,
                    },
                )
            stored_storage_key = stored_object.storage_key
            with observed_span(
                name="document.postgres.persist",
                input={
                    "document_id": str(file_id),
                    "file_metadata_id": str(file_id),
                    "extension": normalized_extension,
                    "content_type": upload_input.content_type,
                    "size_bytes": stored_object.size_bytes,
                    "status": DocumentStatus.UPLOADED.value,
                },
            ) as observation:
                record = await self._document_repository.create_uploaded_document(
                    UploadedDocumentCreate(
                        user_id=self._user_id,
                        document_id=file_id,
                        file_metadata_id=file_id,
                        original_filename=upload_input.original_filename,
                        storage_key=stored_object.storage_key,
                        storage_backend=self._storage_backend,
                        content_type=upload_input.content_type,
                        normalized_extension=normalized_extension,
                        size_bytes=stored_object.size_bytes,
                        checksum_sha256=checksum_sha256,
                        document_status=DocumentStatus.UPLOADED,
                        file_storage_status=FileStorageStatus.STORED,
                    ),
                )
                safe_update_observation(
                    observation,
                    output={
                        "document_id": str(record.document_id),
                        "file_metadata_id": str(record.file_metadata_id),
                        "status": record.status,
                    },
                )
                return record
        except Exception:
            if stored_storage_key is not None:
                with observed_span(
                    name="document.storage.compensating_delete",
                    input={"storage_backend": self._storage_backend},
                ) as observation:
                    self._cleanup_stored_object(stored_storage_key)
                    safe_update_observation(
                        observation,
                        output={"status": "attempted"},
                    )
            raise

    @staticmethod
    def _validate_extension(filename: str) -> str:
        extension = PurePath(filename).suffix.lower()
        if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
            raise UnsupportedUploadFileTypeError(
                filename=filename,
                extension=extension or None,
            )

        return extension

    def _build_storage_key(self, file_id: uuid.UUID, extension: str) -> str:
        return f"users/{self._user_id}/documents/{file_id}/source/content{extension}"

    def _validate_size(self, filename: str, size_bytes: int) -> None:
        if self._max_upload_bytes is None:
            return
        if size_bytes > self._max_upload_bytes:
            raise UploadTooLargeError(
                filename=filename,
                size_bytes=size_bytes,
                max_upload_bytes=self._max_upload_bytes,
            )

    def _cleanup_stored_object(self, storage_key: str) -> None:
        try:
            self._storage_provider.delete(storage_key)
        except Exception:
            logger.warning(
                "Failed to clean up stored object after metadata persistence "
                "failure: %s",
                storage_key,
                exc_info=True,
            )
