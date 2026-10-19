"""File guide.

- Use: Tests synchronous upload-to-index document ingestion behavior.
- Usage: Run with pytest for document ingestion service changes.
- Duties: Uses fakes for storage, repository, loaders, embeddings, and vector store.
- Depends on: Project modules: rastin_ai.database.enums,
  rastin_ai.rag, rastin_ai.repositories.documents, and
  rastin_ai.services.
"""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import rastin_ai.observability.langfuse as langfuse_observability
from rastin_ai.database.enums import DocumentStatus, FileStorageStatus
from rastin_ai.rag.chunking.recursive import RecursiveTextChunker
from rastin_ai.rag.exceptions import (
    DocumentLoadError,
    EmbeddingError,
    VectorStoreError,
)
from rastin_ai.rag.extraction import MALFORMED_JSON
from rastin_ai.rag.indexing import DocumentIndexer
from rastin_ai.rag.models import Document
from rastin_ai.repositories.documents import (
    UploadedDocumentCreate,
    UploadedDocumentRecord,
)
from rastin_ai.services.document_ingestion import (
    EMBEDDING_FAILED,
    EXTRACTION_FAILED,
    VECTOR_STORE_FAILED,
    SynchronousDocumentIngestionService,
)
from rastin_ai.services.documents import DocumentUpload, StoredDocumentService
from rastin_ai.services.upload import UploadService
from rastin_ai.storage.base import StoredObject

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class FakeStorageProvider:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.opened_keys: list[str] = []
        self.deleted_keys: list[str] = []

    def save(self, storage_key: str, content: bytes) -> StoredObject:
        self.objects[storage_key] = content
        return StoredObject(storage_key=storage_key, size_bytes=len(content))

    def open(self, storage_key: str) -> bytes:
        self.opened_keys.append(storage_key)
        return self.objects[storage_key]

    def read(self, storage_key: str) -> bytes:
        return self.open(storage_key)

    def delete(self, storage_key: str) -> None:
        self.deleted_keys.append(storage_key)
        self.objects.pop(storage_key, None)

    def exists(self, storage_key: str) -> bool:
        return storage_key in self.objects


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, UploadedDocumentRecord] = {}
        self.created: list[UploadedDocumentCreate] = []
        self.status_updates: list[tuple[UUID, DocumentStatus, str | None]] = []

    async def create_uploaded_document(
        self,
        document: UploadedDocumentCreate,
    ) -> UploadedDocumentRecord:
        record = UploadedDocumentRecord(
            user_id=document.user_id,
            document_id=document.document_id,
            session_id=uuid4(),
            file_metadata_id=document.file_metadata_id,
            filename=document.original_filename,
            content_type=document.content_type,
            normalized_extension=document.normalized_extension,
            storage_key=document.storage_key,
            storage_backend=document.storage_backend,
            size_bytes=document.size_bytes,
            checksum_sha256=document.checksum_sha256,
            status=document.document_status.value,
            indexing_error_code=None,
            indexing_error_message=None,
            file_storage_status=document.file_storage_status.value,
            created_at=NOW,
            updated_at=NOW,
        )
        self.created.append(document)
        self.records[record.document_id] = record
        return record

    async def get_by_id(
        self,
        document_id: UUID,
        *,
        user_id: UUID,
    ) -> UploadedDocumentRecord | None:
        record = self.records.get(document_id)
        if record is None or record.user_id != user_id:
            return None
        return record

    async def list_uploaded_documents(
        self,
        *,
        user_id: UUID,
    ) -> list[UploadedDocumentRecord]:
        return [record for record in self.records.values() if record.user_id == user_id]

    async def update_status(
        self,
        document_id: UUID,
        status: DocumentStatus,
        *,
        user_id: UUID,
        indexing_error_code: str | None = None,
        indexing_error_message: str | None = None,
    ) -> UploadedDocumentRecord:
        self.status_updates.append((document_id, status, indexing_error_code))
        record = self.records[document_id]
        assert record.user_id == user_id
        updated = UploadedDocumentRecord(
            user_id=record.user_id,
            document_id=record.document_id,
            session_id=record.session_id,
            file_metadata_id=record.file_metadata_id,
            filename=record.filename,
            content_type=record.content_type,
            normalized_extension=record.normalized_extension,
            storage_key=record.storage_key,
            storage_backend=record.storage_backend,
            size_bytes=record.size_bytes,
            checksum_sha256=record.checksum_sha256,
            status=status.value,
            indexing_error_code=indexing_error_code,
            indexing_error_message=indexing_error_message,
            file_storage_status=record.file_storage_status,
            created_at=record.created_at,
            updated_at=NOW,
        )
        self.records[document_id] = updated
        return updated


class FakeLoader:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.paths: list[Path] = []

    def load(self, path: str | Path) -> list[Document]:
        self.paths.append(Path(path))
        if self.fail:
            msg = "could not extract text"
            raise DocumentLoadError(msg)
        return [
            Document(
                id="loader-doc-1",
                text="alpha beta gamma",
                source=str(path),
                metadata={"filename": Path(path).name},
            )
        ]


class FakeEmbeddingProvider:
    dimension = 2

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.texts: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            msg = "embedding failed"
            raise EmbeddingError(msg)
        self.texts.extend(texts)
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


class FakeVectorStore:
    def __init__(self, *, fail_upsert: bool = False) -> None:
        self.fail_upsert = fail_upsert
        self.deleted_document_ids: list[str] = []
        self.deleted_user_ids: list[str | None] = []
        self.upserts = []
        self.active_chunks_by_document_id: dict[str, list[str]] = {}

    def upsert(self, chunks, embeddings) -> None:
        if self.fail_upsert:
            msg = "qdrant failed"
            raise VectorStoreError(msg)
        self.upserts.append((chunks, embeddings))
        for chunk in chunks:
            self.active_chunks_by_document_id.setdefault(chunk.document_id, []).append(
                chunk.id
            )

    def search(self, *args, **kwargs):
        return []

    def delete(self, *, chunk_ids=None, document_id=None, user_id=None) -> None:
        if document_id is not None:
            self.deleted_document_ids.append(document_id)
            self.deleted_user_ids.append(user_id)
            self.active_chunks_by_document_id[document_id] = []


def test_successful_upload_to_index_flow() -> None:
    result, repository, storage, _, embedder, vector_store = asyncio.run(
        _run_upload_to_index(),
    )

    assert result.status == DocumentStatus.INDEXED.value
    assert result.indexing_error_code is None
    assert result.checksum_sha256 == hashlib.sha256(b"alpha beta gamma").hexdigest()
    assert storage.opened_keys == [
        f"users/{USER_ID}/documents/{DOCUMENT_ID}/source/content.txt"
    ]
    assert [update[1] for update in repository.status_updates] == [
        DocumentStatus.PROCESSING,
        DocumentStatus.INDEXED,
    ]
    assert embedder.texts == ["alpha beta gamma"]
    assert len(vector_store.upserts) == 1


def test_qdrant_payload_uses_logical_document_uuid() -> None:
    result, _, _, _, _, vector_store = asyncio.run(_run_upload_to_index())

    chunks, _ = vector_store.upserts[0]
    assert chunks[0].document_id == str(result.document_id)
    assert chunks[0].metadata["document_id"] == str(result.document_id)
    assert chunks[0].metadata["user_id"] == str(USER_ID)
    assert chunks[0].metadata["file_metadata_id"] == str(DOCUMENT_ID)


def test_extraction_failure_updates_document_to_failed() -> None:
    loader = FakeLoader(fail=True)
    result, repository, storage, _, _, _ = asyncio.run(
        _run_upload_to_index(loader=loader),
    )

    assert result.status == DocumentStatus.FAILED.value
    assert result.indexing_error_code == EXTRACTION_FAILED
    assert result.indexing_error_message == "could not extract text"
    assert (
        storage.exists(f"users/{USER_ID}/documents/{DOCUMENT_ID}/source/content.txt")
        is True
    )
    assert repository.records[DOCUMENT_ID].file_metadata_id == DOCUMENT_ID


def test_embedding_failure_updates_document_to_failed() -> None:
    embedder = FakeEmbeddingProvider(fail=True)
    result, _, storage, _, _, _ = asyncio.run(_run_upload_to_index(embedder=embedder))

    assert result.status == DocumentStatus.FAILED.value
    assert result.indexing_error_code == EMBEDDING_FAILED
    assert (
        storage.exists(f"users/{USER_ID}/documents/{DOCUMENT_ID}/source/content.txt")
        is True
    )


def test_qdrant_failure_updates_document_to_failed() -> None:
    vector_store = FakeVectorStore(fail_upsert=True)
    result, _, storage, _, _, _ = asyncio.run(
        _run_upload_to_index(vector_store=vector_store),
    )

    assert result.status == DocumentStatus.FAILED.value
    assert result.indexing_error_code == VECTOR_STORE_FAILED
    assert (
        storage.exists(f"users/{USER_ID}/documents/{DOCUMENT_ID}/source/content.txt")
        is True
    )


def test_retry_reindex_deletes_prior_document_chunks_before_upsert() -> None:
    vector_store = FakeVectorStore()
    _, repository, _, record, _, _ = asyncio.run(
        _run_upload_to_index(vector_store=vector_store),
    )
    storage = FakeStorageProvider()
    storage.objects[record.storage_key] = b"alpha beta gamma"
    ingestion = _ingestion_service(repository, storage, vector_store)

    asyncio.run(ingestion.index_uploaded_document(record))

    assert vector_store.deleted_document_ids == [str(DOCUMENT_ID), str(DOCUMENT_ID)]
    assert vector_store.deleted_user_ids == [str(USER_ID), str(USER_ID)]
    assert len(vector_store.active_chunks_by_document_id[str(DOCUMENT_ID)]) == 1


def test_csv_upload_indexes_through_shared_extractor() -> None:
    result, repository, storage, vector_store = asyncio.run(_run_csv_upload_to_index())

    assert result.status == DocumentStatus.INDEXED.value
    assert result.indexing_error_code is None
    assert (
        storage.exists(f"users/{USER_ID}/documents/{DOCUMENT_ID}/source/content.csv")
        is True
    )
    assert repository.records[DOCUMENT_ID].file_metadata_id == DOCUMENT_ID
    assert repository.records[DOCUMENT_ID].file_storage_status == (
        FileStorageStatus.STORED.value
    )
    chunks, _ = vector_store.upserts[0]
    assert chunks[0].document_id == str(DOCUMENT_ID)
    assert chunks[0].metadata["document_id"] == str(DOCUMENT_ID)
    assert chunks[0].metadata["file_type"] == "csv"
    assert chunks[0].metadata["row_start"] == 2
    assert chunks[0].metadata["row_end"] == 2
    assert chunks[0].metadata["columns"] == ["a", "b"]


def test_malformed_json_upload_fails_without_deleting_file_or_metadata() -> None:
    result, repository, storage, _ = asyncio.run(
        _run_real_extractor_upload(
            filename="broken.json",
            content=b'{"a": ',
            content_type="application/json",
        )
    )

    assert result.status == DocumentStatus.FAILED.value
    assert result.indexing_error_code == MALFORMED_JSON
    assert (
        storage.exists(f"users/{USER_ID}/documents/{DOCUMENT_ID}/source/content.json")
        is True
    )
    assert repository.records[DOCUMENT_ID].file_metadata_id == DOCUMENT_ID
    assert repository.records[DOCUMENT_ID].file_storage_status == (
        FileStorageStatus.STORED.value
    )


def test_upload_to_index_records_safe_observability_spans(monkeypatch) -> None:
    from test_observability import FakeLangfuseClient

    fake_client = FakeLangfuseClient()
    monkeypatch.setattr(
        langfuse_observability,
        "_get_langfuse_client",
        lambda settings=None: fake_client,
    )

    asyncio.run(_run_upload_to_index())

    names = [
        observation.start_kwargs["name"] for observation in fake_client.observations
    ]
    assert "document.upload_index" in names
    assert "document.storage.write" in names
    assert "document.postgres.persist" in names
    assert "document.storage.read" in names
    assert "document.extraction.load" in names
    assert "document.chunk" in names
    assert "document.embedding" in names
    assert "qdrant.delete_document_chunks" in names
    assert "qdrant.upsert_document_chunks" in names
    assert "document.lifecycle.indexed" in names
    serialized = str(
        [
            observation.start_kwargs
            for observation in fake_client.observations
            if observation.start_kwargs["name"] != "document.postgres.persist"
        ]
    )
    assert (
        f"users/{USER_ID}/documents/{DOCUMENT_ID}/source/content.txt" not in serialized
    )


async def _run_csv_upload_to_index():
    return await _run_real_extractor_upload(
        filename="data.csv",
        content=b"a,b\n1,2\n",
        content_type="text/csv",
    )


async def _run_real_extractor_upload(
    *,
    filename: str,
    content: bytes,
    content_type: str,
):
    storage = FakeStorageProvider()
    repository = FakeDocumentRepository()
    vector_store = FakeVectorStore()
    upload_service = UploadService(
        storage,
        repository,
        user_id=USER_ID,
        file_id_factory=lambda: DOCUMENT_ID,
    )
    ingestion = SynchronousDocumentIngestionService(
        storage_provider=storage,
        document_repository=repository,
        indexer_factory=lambda selected_loader: DocumentIndexer(
            loader=selected_loader,
            chunker=RecursiveTextChunker(chunk_size=50, chunk_overlap=0),
            embedding_provider=FakeEmbeddingProvider(),
            vector_store=vector_store,
        ),
    )
    document_service = StoredDocumentService(
        upload_service=upload_service,
        document_repository=repository,
        ingestion_service=ingestion,
        user_id=USER_ID,
    )

    result = await document_service.upload_document(
        DocumentUpload(
            filename=filename,
            content=content,
            content_type=content_type,
        ),
    )
    return result, repository, storage, vector_store


async def _run_upload_to_index(
    *,
    filename: str = "notes.txt",
    content: bytes = b"alpha beta gamma",
    loader: FakeLoader | None = None,
    embedder: FakeEmbeddingProvider | None = None,
    vector_store: FakeVectorStore | None = None,
):
    storage = FakeStorageProvider()
    repository = FakeDocumentRepository()
    upload_service = UploadService(
        storage,
        repository,
        user_id=USER_ID,
        file_id_factory=lambda: DOCUMENT_ID,
    )
    ingestion = _ingestion_service(
        repository,
        storage,
        vector_store or FakeVectorStore(),
        loader=loader,
        embedder=embedder,
    )
    document_service = StoredDocumentService(
        upload_service=upload_service,
        document_repository=repository,
        ingestion_service=ingestion,
        user_id=USER_ID,
    )

    result = await document_service.upload_document(
        DocumentUpload(filename=filename, content=content, content_type="text/plain"),
    )
    record = await repository.get_by_id(result.document_id, user_id=USER_ID)
    assert record is not None
    return (
        result,
        repository,
        storage,
        record,
        ingestion._embedder,
        ingestion._vector_store,
    )


def _ingestion_service(
    repository: FakeDocumentRepository,
    storage: FakeStorageProvider,
    vector_store: FakeVectorStore,
    *,
    loader: FakeLoader | None = None,
    embedder: FakeEmbeddingProvider | None = None,
):
    test_loader = loader or FakeLoader()
    test_embedder = embedder or FakeEmbeddingProvider()

    class IngestionService(SynchronousDocumentIngestionService):
        _embedder = test_embedder
        _vector_store = vector_store

    return IngestionService(
        storage_provider=storage,
        document_repository=repository,
        loader_factory=lambda _extension: test_loader,
        indexer_factory=lambda selected_loader: DocumentIndexer(
            loader=selected_loader,
            chunker=RecursiveTextChunker(chunk_size=50, chunk_overlap=0),
            embedding_provider=test_embedder,
            vector_store=vector_store,
        ),
    )
