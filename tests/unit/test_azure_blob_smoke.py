"""File guide.

- Use: Contains unit tests for the Azure Blob storage smoke runner.
- Usage: Run this file with pytest when checking smoke-test behavior.
- Duties: Uses fake storage providers to verify smoke-test operations and cleanup.
- Depends on: Project modules: rastin_ai.storage.azure_blob_smoke,
  rastin_ai.storage.base, and rastin_ai.storage.exceptions.
"""

import pytest

from rastin_ai.storage.azure_blob_smoke import (
    SMOKE_TEST_CONTENT,
    StorageSmokeTestError,
    run_storage_provider_smoke_test,
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


def test_storage_provider_smoke_test_runs_all_operations_and_cleans_up() -> None:
    provider = FakeStorageProvider()
    storage_key = "smoke-tests/test-id/hello.txt"

    result = run_storage_provider_smoke_test(provider, storage_key=storage_key)

    assert result == {
        "status": "ok",
        "backend": "azure_blob",
        "content_size_bytes": len(SMOKE_TEST_CONTENT),
        "operations": {
            "save": True,
            "exists_after_save": True,
            "read": True,
            "delete": True,
            "exists_after_delete": False,
        },
        "cleanup": {
            "attempted": True,
            "succeeded": True,
        },
    }
    assert provider.deleted_keys == [storage_key]
    assert provider.exists(storage_key) is False


def test_storage_provider_smoke_test_uses_temporary_key_when_not_provided() -> None:
    provider = FakeStorageProvider()

    run_storage_provider_smoke_test(provider)

    assert len(provider.deleted_keys) == 1
    assert provider.deleted_keys[0].startswith("smoke-tests/")
    assert provider.deleted_keys[0].endswith("/hello.txt")


def test_storage_provider_smoke_test_cleans_up_after_failure() -> None:
    provider = MismatchedReadStorageProvider()
    storage_key = "smoke-tests/test-id/hello.txt"

    with pytest.raises(StorageSmokeTestError) as exc_info:
        run_storage_provider_smoke_test(provider, storage_key=storage_key)

    assert exc_info.value.result["status"] == "failed"
    assert exc_info.value.result["operations"]["read"] is False
    assert exc_info.value.result["cleanup"] == {
        "attempted": True,
        "succeeded": True,
    }
    assert provider.deleted_keys == [storage_key]
    assert provider.exists(storage_key) is False
