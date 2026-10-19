"""File guide.

- Use: Contains unit tests for upload service behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.database.enums,
  rastin_ai.repositories.documents, rastin_ai.services.upload,
  rastin_ai.storage.base, and rastin_ai.storage.exceptions.
"""

import asyncio
import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from rastin_ai.database.enums import DocumentStatus, FileStorageStatus
from rastin_ai.repositories.documents import (
    UploadedDocumentCreate,
    UploadedDocumentRecord,
)
from rastin_ai.services.upload import (
    UnsupportedUploadFileTypeError,
    UploadInput,
    UploadService,
    UploadTooLargeError,
)
from rastin_ai.storage.base import StoredObject
from rastin_ai.storage.exceptions import StorageError

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


class FakeStorageProvider:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted_keys: list[str] = []
        self.fail_save = False
        self.fail_delete = False

    def save(self, storage_key: str, content: bytes) -> StoredObject:
        if self.fail_save:
            msg = "storage failed"
            raise StorageError(msg)
        self.objects[storage_key] = content
        return StoredObject(storage_key=storage_key, size_bytes=len(content))

    def open(self, storage_key: str) -> bytes:
        return self.objects[storage_key]

    def delete(self, storage_key: str) -> None:
        if self.fail_delete:
            msg = "cleanup failed"
            raise StorageError(msg)
        self.deleted_keys.append(storage_key)
        self.objects.pop(storage_key, None)

    def exists(self, storage_key: str) -> bool:
        return storage_key in self.objects


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, UploadedDocumentRecord] = {}
        self.created: list[UploadedDocumentCreate] = []
        self.fail_create = False

    async def create_uploaded_document(
        self,
        document: UploadedDocumentCreate,
    ) -> UploadedDocumentRecord:
        if self.fail_create:
            msg = "metadata failed"
            raise RuntimeError(msg)
        now = datetime.now(UTC)
        record = UploadedDocumentRecord(
            user_id=document.user_id,
            document_id=document.document_id,
            session_id=uuid4(),
            file_metadata_id=document.file_metadata_id,
            filename=document.original_filename,
            storage_key=document.storage_key,
            storage_backend=document.storage_backend,
            content_type=document.content_type,
            normalized_extension=document.normalized_extension,
            size_bytes=document.size_bytes,
            checksum_sha256=document.checksum_sha256,
            status=document.document_status.value,
            indexing_error_code=None,
            indexing_error_message=None,
            file_storage_status=document.file_storage_status.value,
            created_at=now,
            updated_at=now,
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


def run_upload(
    service: UploadService,
    upload_input: UploadInput,
) -> UploadedDocumentRecord:
    return asyncio.run(service.upload(upload_input))


def test_upload_service_stores_supported_upload_and_metadata() -> None:
    storage = FakeStorageProvider()
    repository = FakeDocumentRepository()
    file_id = UUID("11111111-1111-4111-8111-111111111111")
    service = UploadService(
        storage,
        repository,
        user_id=USER_ID,
        file_id_factory=lambda: file_id,
    )

    record = run_upload(
        service,
        UploadInput("Report.PDF", b"pdf bytes", "application/pdf"),
    )

    assert record.document_id == file_id
    assert record.file_metadata_id == file_id
    assert record.filename == "Report.PDF"
    assert record.user_id == USER_ID
    assert record.storage_key == (
        f"users/{USER_ID}/documents/{file_id}/source/content.pdf"
    )
    assert record.storage_backend == "local"
    assert record.content_type == "application/pdf"
    assert record.normalized_extension == ".pdf"
    assert record.size_bytes == len(b"pdf bytes")
    assert record.checksum_sha256 == hashlib.sha256(b"pdf bytes").hexdigest()
    assert record.status == DocumentStatus.UPLOADED.value
    assert record.file_storage_status == FileStorageStatus.STORED.value
    assert storage.open(record.storage_key) == b"pdf bytes"
    assert repository.created[0].document_status is DocumentStatus.UPLOADED
    assert repository.created[0].file_storage_status is FileStorageStatus.STORED


def test_upload_service_duplicate_filenames_get_unique_ids_and_storage_keys() -> None:
    storage = FakeStorageProvider()
    repository = FakeDocumentRepository()
    ids = iter(
        [
            UUID("11111111-1111-4111-8111-111111111111"),
            UUID("22222222-2222-4222-8222-222222222222"),
        ]
    )
    service = UploadService(
        storage,
        repository,
        user_id=USER_ID,
        file_id_factory=lambda: next(ids),
    )

    first = run_upload(service, UploadInput("same.csv", b"first"))
    second = run_upload(service, UploadInput("same.csv", b"second"))

    assert first.document_id != second.document_id
    assert first.storage_key != second.storage_key
    assert storage.open(first.storage_key) == b"first"
    assert storage.open(second.storage_key) == b"second"


def test_upload_service_accepts_json_upload() -> None:
    storage = FakeStorageProvider()
    repository = FakeDocumentRepository()
    file_id = UUID("33333333-3333-4333-8333-333333333333")
    service = UploadService(
        storage,
        repository,
        user_id=USER_ID,
        file_id_factory=lambda: file_id,
    )

    record = run_upload(
        service,
        UploadInput("payload.JSON", b'{"ok": true}', "application/json"),
    )

    assert record.storage_key == (
        f"users/{USER_ID}/documents/{file_id}/source/content.json"
    )
    assert record.content_type == "application/json"
    assert record.normalized_extension == ".json"
    assert storage.open(record.storage_key) == b'{"ok": true}'


def test_upload_service_rejects_unsupported_extension() -> None:
    service = UploadService(
        FakeStorageProvider(),
        FakeDocumentRepository(),
        user_id=USER_ID,
    )

    with pytest.raises(UnsupportedUploadFileTypeError) as exc_info:
        run_upload(service, UploadInput("malware.exe", b"nope"))

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "UNSUPPORTED_UPLOAD_FILE_TYPE"


def test_upload_service_propagates_storage_provider_failure() -> None:
    storage = FakeStorageProvider()
    storage.fail_save = True
    repository = FakeDocumentRepository()
    service = UploadService(storage, repository, user_id=USER_ID)

    with pytest.raises(StorageError):
        run_upload(service, UploadInput("report.pdf", b"data"))

    assert repository.created == []
    assert storage.deleted_keys == []


def test_upload_service_cleans_up_stored_object_when_metadata_fails_before_commit() -> (
    None
):
    storage = FakeStorageProvider()
    repository = FakeDocumentRepository()
    repository.fail_create = True
    file_id = UUID("11111111-1111-4111-8111-111111111111")
    service = UploadService(
        storage,
        repository,
        user_id=USER_ID,
        file_id_factory=lambda: file_id,
    )

    with pytest.raises(RuntimeError, match="metadata failed"):
        run_upload(service, UploadInput("report.md", b"# report"))

    storage_key = f"users/{USER_ID}/documents/{file_id}/source/content.md"
    assert storage.deleted_keys == [storage_key]
    assert storage.exists(storage_key) is False


def test_upload_service_reraises_metadata_error_when_cleanup_delete_fails() -> None:
    storage = FakeStorageProvider()
    storage.fail_delete = True
    repository = FakeDocumentRepository()
    repository.fail_create = True
    file_id = UUID("11111111-1111-4111-8111-111111111111")
    service = UploadService(
        storage,
        repository,
        user_id=USER_ID,
        file_id_factory=lambda: file_id,
    )

    with pytest.raises(RuntimeError, match="metadata failed"):
        run_upload(service, UploadInput("report.md", b"# report"))

    assert (
        storage.exists(f"users/{USER_ID}/documents/{file_id}/source/content.md") is True
    )


def test_upload_service_accepts_zero_byte_upload() -> None:
    service = UploadService(
        FakeStorageProvider(),
        FakeDocumentRepository(),
        user_id=USER_ID,
    )

    record = run_upload(service, UploadInput("empty.txt", b""))

    assert record.size_bytes == 0


def test_upload_service_rejects_upload_above_configured_size() -> None:
    storage = FakeStorageProvider()
    repository = FakeDocumentRepository()
    service = UploadService(
        storage,
        repository,
        user_id=USER_ID,
        max_upload_bytes=4,
    )

    with pytest.raises(UploadTooLargeError) as exc_info:
        run_upload(service, UploadInput("report.txt", b"12345"))

    assert exc_info.value.status_code == 413
    assert exc_info.value.error_code == "UPLOAD_TOO_LARGE"
    assert exc_info.value.details == {
        "filename": "report.txt",
        "size_bytes": 5,
        "max_upload_bytes": 4,
    }
    assert storage.objects == {}
    assert repository.created == []


def test_fake_repository_get_by_id_returns_created_document() -> None:
    repository = FakeDocumentRepository()
    document = UploadedDocumentCreate(
        user_id=USER_ID,
        document_id=uuid4(),
        file_metadata_id=uuid4(),
        original_filename="notes.txt",
        storage_key=f"users/{USER_ID}/documents/x/source/content.txt",
        storage_backend="local",
        content_type="text/plain",
        normalized_extension=".txt",
        size_bytes=5,
        checksum_sha256=hashlib.sha256(b"notes").hexdigest(),
    )

    record = asyncio.run(repository.create_uploaded_document(document))

    assert asyncio.run(
        repository.get_by_id(record.document_id, user_id=USER_ID)
    ) == replace(record)
