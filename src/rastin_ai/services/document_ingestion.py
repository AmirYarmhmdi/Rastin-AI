"""File guide.

- Use: Runs synchronous document ingestion after upload persistence.
- Usage: Import DocumentIngestionService and SynchronousDocumentIngestionService
  from rastin_ai.services.document_ingestion.
- Duties: Reads stored files, selects the existing loader/indexer path, and
  updates document lifecycle status.
- Depends on: Project modules: rastin_ai.database.enums,
  rastin_ai.rag, rastin_ai.repositories.documents, and
  rastin_ai.storage.base.
"""

import logging
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol
from uuid import UUID

from rastin_ai.database.enums import DocumentStatus
from rastin_ai.observability import observed_span, safe_update_observation
from rastin_ai.rag.exceptions import (
    DocumentLoadError,
    EmbeddingError,
    EmptyDocumentError,
    RAGError,
    VectorStoreError,
)
from rastin_ai.rag.extraction import (
    SUPPORTED_EXTRACTION_EXTENSIONS,
    DocumentExtractionError,
    SharedDocumentLoader,
)
from rastin_ai.rag.indexing import DocumentIndexer
from rastin_ai.rag.loaders.base import DocumentLoader
from rastin_ai.repositories.documents import (
    DocumentRepository,
    UploadedDocumentRecord,
)
from rastin_ai.storage.base import StorageProvider
from rastin_ai.storage.exceptions import StorageError

logger = logging.getLogger(__name__)

INDEXABLE_EXTENSIONS = SUPPORTED_EXTRACTION_EXTENSIONS
UNSUPPORTED_INDEXING_FORMAT = "UNSUPPORTED_INDEXING_FORMAT"
STORAGE_READ_FAILED = "STORAGE_READ_FAILED"
EXTRACTION_FAILED = "EXTRACTION_FAILED"
EMBEDDING_FAILED = "EMBEDDING_FAILED"
VECTOR_STORE_FAILED = "VECTOR_STORE_FAILED"
INDEXING_FAILED = "INDEXING_FAILED"


class DocumentIngestionService(Protocol):
    async def index_uploaded_document(
        self,
        document: UploadedDocumentRecord,
    ) -> UploadedDocumentRecord:
        """Synchronously index a persisted uploaded document."""


class SynchronousDocumentIngestionService:
    """Index uploaded documents in-process for the MVP runtime."""

    def __init__(
        self,
        *,
        storage_provider: StorageProvider,
        document_repository: DocumentRepository,
        indexer_factory: Callable[[DocumentLoader], DocumentIndexer],
        loader_factory: Callable[[str], DocumentLoader] | None = None,
    ) -> None:
        self._storage_provider = storage_provider
        self._document_repository = document_repository
        self._indexer_factory = indexer_factory
        self._loader_factory = loader_factory or _loader_for

    async def index_uploaded_document(
        self,
        document: UploadedDocumentRecord,
    ) -> UploadedDocumentRecord:
        with observed_span(
            name="document.lifecycle.processing",
            input={
                "document_id": str(document.document_id),
                "previous_status": document.status,
            },
        ) as observation:
            processing_record = await self._document_repository.update_status(
                document.document_id,
                DocumentStatus.PROCESSING,
                user_id=_require_user_id(document),
            )
            safe_update_observation(
                observation,
                output={"status": processing_record.status},
            )

        try:
            loader = self._loader_factory(document.normalized_extension)
            with observed_span(
                name="document.storage.read",
                input={
                    "document_id": str(document.document_id),
                    "storage_backend": document.storage_backend,
                    "extension": document.normalized_extension,
                },
            ) as observation:
                content = self._storage_provider.open(document.storage_key)
                safe_update_observation(
                    observation,
                    output={"size_bytes": len(content), "status": "read"},
                )
            with tempfile.TemporaryDirectory(prefix="rastin_ai-index-") as directory:
                path = self._write_loader_file(
                    Path(directory),
                    document.document_id,
                    document.normalized_extension,
                    content,
                )
                indexer = self._indexer_factory(loader)
                indexer.index(
                    path,
                    document_id=str(document.document_id),
                    user_id=str(_require_user_id(document)),
                    replace_existing=True,
                    metadata={
                        "source": document.storage_key,
                        "user_id": str(_require_user_id(document)),
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
                "Document indexing failed",
                extra={
                    "document_id": str(document.document_id),
                    "indexing_error_code": code,
                },
                exc_info=True,
            )
            with observed_span(
                name="document.lifecycle.failed",
                input={"document_id": str(document.document_id), "error_code": code},
            ) as observation:
                failed_record = await self._document_repository.update_status(
                    document.document_id,
                    DocumentStatus.FAILED,
                    user_id=_require_user_id(document),
                    indexing_error_code=code,
                    indexing_error_message=message,
                )
                safe_update_observation(
                    observation,
                    output={
                        "status": failed_record.status,
                        "indexing_error_code": failed_record.indexing_error_code,
                    },
                )
                return failed_record

        with observed_span(
            name="document.lifecycle.indexed",
            input={"document_id": str(document.document_id)},
        ) as observation:
            indexed_record = await self._document_repository.update_status(
                document.document_id,
                DocumentStatus.INDEXED,
                user_id=_require_user_id(document),
            )
            safe_update_observation(
                observation,
                output={"status": indexed_record.status},
            )
            return indexed_record

    @staticmethod
    def _write_loader_file(
        directory: Path,
        document_id: UUID,
        normalized_extension: str,
        content: bytes,
    ) -> Path:
        path = directory / f"{document_id}{normalized_extension}"
        path.write_bytes(content)
        return path


class NonIndexableDocumentError(RAGError):
    """Raised when an accepted upload format has no reliable indexer yet."""


def _loader_for(normalized_extension: str) -> DocumentLoader:
    if normalized_extension in INDEXABLE_EXTENSIONS:
        return SharedDocumentLoader()

    msg = (
        f"Indexing is not available for {normalized_extension or 'unknown'} "
        "uploads in this phase."
    )
    raise NonIndexableDocumentError(msg)


def _require_user_id(document: UploadedDocumentRecord) -> UUID:
    if document.user_id is None:
        msg = f"Document is missing ownership metadata: {document.document_id}"
        raise LookupError(msg)
    return document.user_id


def _failure_details(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, DocumentExtractionError):
        return exc.code, exc.safe_message
    if isinstance(exc, NonIndexableDocumentError):
        return UNSUPPORTED_INDEXING_FORMAT, str(exc)
    if isinstance(exc, StorageError):
        return STORAGE_READ_FAILED, "Stored file could not be read for indexing."
    if isinstance(exc, (DocumentLoadError, EmptyDocumentError, FileNotFoundError)):
        return EXTRACTION_FAILED, _safe_message(exc)
    if isinstance(exc, EmbeddingError):
        return EMBEDDING_FAILED, _safe_message(exc)
    if isinstance(exc, VectorStoreError):
        return VECTOR_STORE_FAILED, _safe_message(exc)
    if isinstance(exc, RAGError):
        return INDEXING_FAILED, _safe_message(exc)
    return INDEXING_FAILED, "Document indexing failed unexpectedly."


def _safe_message(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        message = exc.__class__.__name__
    return message[:512]
