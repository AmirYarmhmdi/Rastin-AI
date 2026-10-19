"""Project-scoped document library services."""

import hashlib
import logging
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Protocol
from uuid import UUID

from fastapi import status

from rastin_ai.core.exceptions import AppException
from rastin_ai.database.enums import DocumentScope, DocumentStatus, FileStorageStatus
from rastin_ai.observability import observed_workflow
from rastin_ai.rag.indexing import DocumentIndexer
from rastin_ai.rag.loaders.base import DocumentLoader
from rastin_ai.rag.vectorstores.base import VectorStore
from rastin_ai.repositories.organizations import RepositoryConflictError
from rastin_ai.repositories.project_documents import (
    ChatAttachmentCreate,
    ProjectDocumentCreate,
    ProjectDocumentRecord,
    ProjectDocumentRepository,
)
from rastin_ai.services.authorization import (
    PROJECT_PERMISSION_CHATS_CREATE,
    PROJECT_PERMISSION_DOCUMENTS_UPLOAD,
    PROJECT_PERMISSION_READ,
    AuthorizationService,
    ProjectAccessContext,
)
from rastin_ai.services.document_ingestion import _failure_details, _loader_for
from rastin_ai.services.upload import (
    SUPPORTED_UPLOAD_EXTENSIONS,
    UnsupportedUploadFileTypeError,
    UploadTooLargeError,
)
from rastin_ai.storage.base import StorageProvider

logger = logging.getLogger(__name__)


class ProjectDocumentNotFoundError(AppException):
    """Raised when a project document cannot be read through the current scope."""

    def __init__(self, document_id: UUID) -> None:
        super().__init__(
            "Project document not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="PROJECT_DOCUMENT_NOT_FOUND",
            details={"document_id": str(document_id)},
        )


class InvalidProjectDocumentUploadError(AppException):
    """Raised when a project document upload is structurally invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_PROJECT_DOCUMENT_UPLOAD",
        )


class ProjectDocumentConflictError(AppException):
    """Raised when project document persistence violates uniqueness."""

    def __init__(self) -> None:
        super().__init__(
            "Project document already exists.",
            status_code=status.HTTP_409_CONFLICT,
            error_code="PROJECT_DOCUMENT_CONFLICT",
        )


@dataclass(frozen=True)
class ProjectDocumentUpload:
    filename: str
    content: bytes
    content_type: str | None = None


class ProjectDocumentService(Protocol):
    async def upload_project_library_document(
        self,
        context: ProjectAccessContext,
        upload: ProjectDocumentUpload,
    ) -> ProjectDocumentRecord:
        """Store and index a project-library document."""

    async def list_project_library_documents(
        self,
        context: ProjectAccessContext,
    ) -> list[ProjectDocumentRecord]:
        """List project-library documents visible to the project member."""

    async def get_project_library_document(
        self,
        context: ProjectAccessContext,
        document_id: UUID,
    ) -> ProjectDocumentRecord:
        """Return one scoped project-library document."""

    async def read_project_library_document(
        self,
        context: ProjectAccessContext,
        document_id: UUID,
    ) -> tuple[ProjectDocumentRecord, bytes]:
        """Read bytes for one scoped project-library document."""

    async def delete_project_library_document(
        self,
        context: ProjectAccessContext,
        document_id: UUID,
    ) -> None:
        """Delete one scoped project-library document."""

    async def upload_chat_attachment_document(
        self,
        context: ProjectAccessContext,
        session_id: UUID,
        upload: ProjectDocumentUpload,
    ) -> ProjectDocumentRecord:
        """Store and index a chat-only attachment for one project session."""


class StoredProjectDocumentService:
    """Project-library document service using dedicated scoped persistence."""

    def __init__(
        self,
        *,
        storage_provider: StorageProvider,
        project_document_repository: ProjectDocumentRepository,
        authorization_service: AuthorizationService,
        vector_store_factory: Callable[[], VectorStore],
        indexer_factory: Callable[[DocumentLoader], DocumentIndexer],
        storage_backend: str,
        max_upload_bytes: int | None = None,
        file_id_factory: Callable[[], uuid.UUID] = uuid.uuid4,
    ) -> None:
        self._storage_provider = storage_provider
        self._project_document_repository = project_document_repository
        self._authorization_service = authorization_service
        self._vector_store_factory = vector_store_factory
        self._indexer_factory = indexer_factory
        self._storage_backend = storage_backend
        self._max_upload_bytes = max_upload_bytes
        self._file_id_factory = file_id_factory

    async def upload_project_library_document(
        self,
        context: ProjectAccessContext,
        upload: ProjectDocumentUpload,
    ) -> ProjectDocumentRecord:
        self._authorization_service.require_project_permission(
            context,
            PROJECT_PERMISSION_DOCUMENTS_UPLOAD,
        )
        filename = " ".join(upload.filename.split())
        if not filename:
            raise InvalidProjectDocumentUploadError(
                "Uploaded project document filename is required."
            )

        normalized_extension = _validate_extension(filename)
        _validate_size(filename, len(upload.content), self._max_upload_bytes)
        file_id = self._file_id_factory()
        storage_key = _build_project_library_storage_key(
            organization_id=context.organization.id,
            project_id=context.project.id,
            file_id=file_id,
            extension=normalized_extension,
        )
        checksum_sha256 = hashlib.sha256(upload.content).hexdigest()
        stored_storage_key: str | None = None

        with observed_workflow(
            name="project_document.upload_index",
            input={
                "organization_id": str(context.organization.id),
                "project_id": str(context.project.id),
                "extension": normalized_extension,
                "content_type": upload.content_type,
                "size_bytes": len(upload.content),
            },
            metadata={
                "workflow_type": "project_document_upload_index",
                "document_scope": DocumentScope.PROJECT_LIBRARY.value,
                "project_id": str(context.project.id),
            },
        ):
            try:
                stored_object = self._storage_provider.save(storage_key, upload.content)
                stored_storage_key = stored_object.storage_key
                create_document = (
                    self._project_document_repository.create_project_library_document
                )
                record = await create_document(
                    ProjectDocumentCreate(
                        document_id=file_id,
                        file_metadata_id=file_id,
                        organization_id=context.organization.id,
                        project_id=context.project.id,
                        uploaded_by_user_id=context.principal.user_id,
                        original_filename=filename,
                        storage_key=stored_object.storage_key,
                        storage_backend=self._storage_backend,
                        content_type=upload.content_type,
                        normalized_extension=normalized_extension,
                        size_bytes=stored_object.size_bytes,
                        checksum_sha256=checksum_sha256,
                        document_status=DocumentStatus.UPLOADED,
                        file_storage_status=FileStorageStatus.STORED,
                    )
                )
            except RepositoryConflictError as exc:
                if stored_storage_key is not None:
                    self._cleanup_stored_object(stored_storage_key)
                raise ProjectDocumentConflictError() from exc
            except Exception:
                if stored_storage_key is not None:
                    self._cleanup_stored_object(stored_storage_key)
                raise

            return await self._index_project_document(record)

    async def list_project_library_documents(
        self,
        context: ProjectAccessContext,
    ) -> list[ProjectDocumentRecord]:
        self._authorization_service.require_project_permission(
            context,
            PROJECT_PERMISSION_READ,
        )
        return await self._project_document_repository.list_project_library_documents(
            organization_id=context.organization.id,
            project_id=context.project.id,
        )

    async def get_project_library_document(
        self,
        context: ProjectAccessContext,
        document_id: UUID,
    ) -> ProjectDocumentRecord:
        self._authorization_service.require_project_permission(
            context,
            PROJECT_PERMISSION_READ,
        )
        record = await self._project_document_repository.get_project_library_document(
            document_id,
            organization_id=context.organization.id,
            project_id=context.project.id,
        )
        if record is None:
            raise ProjectDocumentNotFoundError(document_id)
        return record

    async def read_project_library_document(
        self,
        context: ProjectAccessContext,
        document_id: UUID,
    ) -> tuple[ProjectDocumentRecord, bytes]:
        record = await self.get_project_library_document(context, document_id)
        return record, self._storage_provider.open(record.storage_key)

    async def delete_project_library_document(
        self,
        context: ProjectAccessContext,
        document_id: UUID,
    ) -> None:
        self._authorization_service.require_project_admin(context)
        record = await self.get_project_library_document(context, document_id)
        self._vector_store_factory().delete(
            document_id=str(record.document_id),
            filters={
                "organization_id": str(record.organization_id),
                "project_id": str(record.project_id),
                "document_scope": DocumentScope.PROJECT_LIBRARY.value,
            },
        )
        self._storage_provider.delete(record.storage_key)
        delete_document = (
            self._project_document_repository.delete_project_library_document
        )
        removed = await delete_document(
            record.document_id,
            organization_id=context.organization.id,
            project_id=context.project.id,
        )
        if not removed:
            raise ProjectDocumentNotFoundError(document_id)

    async def upload_chat_attachment_document(
        self,
        context: ProjectAccessContext,
        session_id: UUID,
        upload: ProjectDocumentUpload,
    ) -> ProjectDocumentRecord:
        self._authorization_service.require_project_permission(
            context,
            PROJECT_PERMISSION_CHATS_CREATE,
        )
        filename = " ".join(upload.filename.split())
        if not filename:
            raise InvalidProjectDocumentUploadError(
                "Uploaded chat attachment filename is required."
            )

        normalized_extension = _validate_extension(filename)
        _validate_size(filename, len(upload.content), self._max_upload_bytes)
        document_id = self._file_id_factory()
        storage_key = _build_chat_attachment_storage_key(
            organization_id=context.organization.id,
            project_id=context.project.id,
            session_id=session_id,
            document_id=document_id,
            extension=normalized_extension,
        )
        checksum_sha256 = hashlib.sha256(upload.content).hexdigest()
        stored_storage_key: str | None = None

        with observed_workflow(
            name="project_chat_attachment.upload_index",
            input={
                "organization_id": str(context.organization.id),
                "project_id": str(context.project.id),
                "session_id": str(session_id),
                "extension": normalized_extension,
                "content_type": upload.content_type,
                "size_bytes": len(upload.content),
            },
            metadata={
                "workflow_type": "project_chat_attachment_upload_index",
                "document_scope": DocumentScope.CHAT_ATTACHMENT.value,
                "project_id": str(context.project.id),
                "session_id": str(session_id),
            },
        ):
            try:
                stored_object = self._storage_provider.save(storage_key, upload.content)
                stored_storage_key = stored_object.storage_key
                create_attachment = (
                    self._project_document_repository.create_chat_attachment_document
                )
                record = await create_attachment(
                    ChatAttachmentCreate(
                        document_id=document_id,
                        file_metadata_id=document_id,
                        organization_id=context.organization.id,
                        project_id=context.project.id,
                        uploaded_by_user_id=context.principal.user_id,
                        session_id=session_id,
                        original_filename=filename,
                        storage_key=stored_object.storage_key,
                        storage_backend=self._storage_backend,
                        content_type=upload.content_type,
                        normalized_extension=normalized_extension,
                        size_bytes=stored_object.size_bytes,
                        checksum_sha256=checksum_sha256,
                        document_status=DocumentStatus.UPLOADED,
                        file_storage_status=FileStorageStatus.STORED,
                    )
                )
            except RepositoryConflictError as exc:
                if stored_storage_key is not None:
                    self._cleanup_stored_object(stored_storage_key)
                raise ProjectDocumentConflictError() from exc
            except Exception:
                if stored_storage_key is not None:
                    self._cleanup_stored_object(stored_storage_key)
                raise

            return await self._index_project_document(record)

    async def _index_project_document(
        self,
        document: ProjectDocumentRecord,
    ) -> ProjectDocumentRecord:
        processing_record = await self._project_document_repository.update_status(
            document.document_id,
            organization_id=document.organization_id,
            project_id=document.project_id,
            document_scope=DocumentScope(document.document_scope),
            status=DocumentStatus.PROCESSING,
        )

        try:
            loader = _loader_for(document.normalized_extension)
            content = self._storage_provider.open(document.storage_key)
            with tempfile.TemporaryDirectory(
                prefix="rastin_ai-project-index-"
            ) as directory:
                filename = f"{document.document_id}{document.normalized_extension}"
                path = Path(directory) / filename
                path.write_bytes(content)
                indexer = self._indexer_factory(loader)
                indexer.index(
                    path,
                    document_id=str(document.document_id),
                    user_id=str(document.uploaded_by_user_id),
                    replace_existing=True,
                    metadata={
                        "source": document.storage_key,
                        "user_id": (
                            str(document.uploaded_by_user_id)
                            if document.uploaded_by_user_id is not None
                            else None
                        ),
                        "uploaded_by_user_id": (
                            str(document.uploaded_by_user_id)
                            if document.uploaded_by_user_id is not None
                            else None
                        ),
                        "organization_id": str(document.organization_id),
                        "project_id": str(document.project_id),
                        "document_scope": document.document_scope,
                        "session_id": (
                            str(document.session_id)
                            if document.session_id is not None
                            else None
                        ),
                        "file_metadata_id": str(document.file_metadata_id),
                        "filename": document.filename,
                        "content_type": document.content_type,
                        "storage_key": document.storage_key,
                        "storage_backend": document.storage_backend,
                        "checksum_sha256": document.checksum_sha256,
                    },
                )
        except Exception as exc:
            code, message = _failure_details(exc)
            logger.info(
                "Project document indexing failed",
                extra={
                    "document_id": str(document.document_id),
                    "indexing_error_code": code,
                },
                exc_info=True,
            )
            return await self._project_document_repository.update_status(
                processing_record.document_id,
                organization_id=processing_record.organization_id,
                project_id=processing_record.project_id,
                document_scope=DocumentScope(processing_record.document_scope),
                status=DocumentStatus.FAILED,
                indexing_error_code=code,
                indexing_error_message=message,
            )

        return await self._project_document_repository.update_status(
            processing_record.document_id,
            organization_id=processing_record.organization_id,
            project_id=processing_record.project_id,
            document_scope=DocumentScope(processing_record.document_scope),
            status=DocumentStatus.INDEXED,
        )

    def _cleanup_stored_object(self, storage_key: str) -> None:
        try:
            self._storage_provider.delete(storage_key)
        except Exception:
            logger.warning(
                "Failed to clean up stored project document after persistence "
                "failure: %s",
                storage_key,
                exc_info=True,
            )


def _validate_extension(filename: str) -> str:
    extension = PurePath(filename).suffix.lower()
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise UnsupportedUploadFileTypeError(
            filename=filename,
            extension=extension or None,
        )
    return extension


def _validate_size(
    filename: str,
    size_bytes: int,
    max_upload_bytes: int | None,
) -> None:
    if max_upload_bytes is None or size_bytes <= max_upload_bytes:
        return
    raise UploadTooLargeError(
        filename=filename,
        size_bytes=size_bytes,
        max_upload_bytes=max_upload_bytes,
    )


def _build_project_library_storage_key(
    *,
    organization_id: UUID,
    project_id: UUID,
    file_id: UUID,
    extension: str,
) -> str:
    return (
        f"organizations/{organization_id}/projects/{project_id}/"
        f"library/documents/{file_id}/source/content{extension}"
    )


def _build_chat_attachment_storage_key(
    *,
    organization_id: UUID,
    project_id: UUID,
    session_id: UUID,
    document_id: UUID,
    extension: str,
) -> str:
    return (
        f"organizations/{organization_id}/projects/{project_id}/"
        f"sessions/{session_id}/attachments/{document_id}/source/content{extension}"
    )
