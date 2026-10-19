"""File guide.

- Use: Contains unit tests for Azure Blob persistence verification.
- Usage: Run this file with pytest when checking persistence-test behavior.
- Duties: Uses fake storage providers to verify write/read/delete operations.
- Depends on: Project modules: rastin_ai.storage.azure_blob_persistence and
  rastin_ai.storage.base.
"""

import pytest

from rastin_ai.storage.azure_blob_persistence import (
    PERSISTENCE_TEST_CONTENT,
    StoragePersistenceTestError,
    run_storage_provider_persistence_operation,
)
from rastin_ai.storage.base import StoredObject


class FakeStorageProvider:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted_keys: list[str] = []

    def save(self, storage_key: str, content: bytes) -> StoredObject:
        self.objects[storage_key] = content
        return StoredObject(storage_key=storage_key, size_bytes=len(content))

    def open(self, storage_key: str) -> bytes:
        return self.objects[storage_key]

    def read(self, storage_key: str) -> bytes:
        return self.open(storage_key)

    def delete(self, storage_key: str) -> None:
        self.deleted_keys.append(storage_key)
        self.objects.pop(storage_key, None)

    def exists(self, storage_key: str) -> bool:
        return storage_key in self.objects


class MismatchedReadStorageProvider(FakeStorageProvider):
    def read(self, storage_key: str) -> bytes:
        return b"wrong"


def test_persistence_write_creates_blob_without_deleting_it() -> None:
    provider = FakeStorageProvider()

    result = run_storage_provider_persistence_operation(
        provider,
        operation="write",
        token="phase-14-9-9",
    )

    assert result == {
        "status": "ok",
        "backend": "azure_blob",
        "operation": "write",
        "token": "phase-14-9-9",
        "content_size_bytes": len(PERSISTENCE_TEST_CONTENT),
        "verified": {
            "save": True,
            "exists_after_write": True,
        },
    }
    assert provider.deleted_keys == []
    assert provider.objects["persistence-tests/phase-14-9-9/hello.txt"] == (
        PERSISTENCE_TEST_CONTENT
    )


def test_persistence_read_verifies_existing_blob_content() -> None:
    provider = FakeStorageProvider()
    provider.save(
        "persistence-tests/phase-14-9-9/hello.txt",
        PERSISTENCE_TEST_CONTENT,
    )

    result = run_storage_provider_persistence_operation(
        provider,
        operation="read",
        token="phase-14-9-9",
    )

    assert result["status"] == "ok"
    assert result["operation"] == "read"
    assert result["verified"] == {
        "exists_before_read": True,
        "read": True,
    }


def test_persistence_delete_removes_blob_after_verification() -> None:
    provider = FakeStorageProvider()
    provider.save(
        "persistence-tests/phase-14-9-9/hello.txt",
        PERSISTENCE_TEST_CONTENT,
    )

    result = run_storage_provider_persistence_operation(
        provider,
        operation="delete",
        token="phase-14-9-9",
    )

    assert result["status"] == "ok"
    assert result["operation"] == "delete"
    assert result["verified"] == {
        "delete": True,
        "exists_after_delete": False,
    }
    assert provider.deleted_keys == ["persistence-tests/phase-14-9-9/hello.txt"]
    assert provider.exists("persistence-tests/phase-14-9-9/hello.txt") is False


def test_persistence_read_fails_when_content_does_not_match() -> None:
    provider = MismatchedReadStorageProvider()
    provider.save(
        "persistence-tests/phase-14-9-9/hello.txt",
        PERSISTENCE_TEST_CONTENT,
    )

    with pytest.raises(StoragePersistenceTestError) as exc_info:
        run_storage_provider_persistence_operation(
            provider,
            operation="read",
            token="phase-14-9-9",
        )

    assert exc_info.value.result["status"] == "failed"
    assert exc_info.value.result["verified"] == {
        "exists_before_read": True,
        "read": False,
    }


@pytest.mark.parametrize(
    "token",
    (
        "",
        "contains/slash",
        r"contains\backslash",
        "../escape",
        " token-with-space ",
    ),
)
def test_persistence_rejects_unsafe_tokens(token: str) -> None:
    with pytest.raises(ValueError, match="Token must"):
        run_storage_provider_persistence_operation(
            FakeStorageProvider(),
            operation="write",
            token=token,
        )
