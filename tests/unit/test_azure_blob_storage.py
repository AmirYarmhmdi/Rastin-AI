"""File guide.

- Use: Contains unit tests for Azure Blob storage behavior.
- Usage: Run this file with pytest when checking Azure storage behavior.
- Duties: Builds fake Azure clients and checks provider semantics.
- Depends on: External packages: azure-core, and pytest. Project modules:
  rastin_ai.storage.azure_blob, and rastin_ai.storage.exceptions.
"""

import pytest
from azure.core.exceptions import ResourceNotFoundError

from rastin_ai.storage.azure_blob import AzureBlobStorageProvider
from rastin_ai.storage.exceptions import (
    InvalidStorageKeyError,
    StorageObjectNotFoundError,
)


class FakeDownloadStream:
    def __init__(self, content: bytes) -> None:
        self._content = content

    async def readall(self) -> bytes:
        return self._content


class FakeBlobClient:
    def __init__(self, objects: dict[str, bytes], storage_key: str) -> None:
        self._objects = objects
        self._storage_key = storage_key

    async def upload_blob(self, content: bytes, *, overwrite: bool) -> None:
        assert overwrite is True
        self._objects[self._storage_key] = content

    async def download_blob(self) -> FakeDownloadStream:
        if self._storage_key not in self._objects:
            raise ResourceNotFoundError(message="not found")
        return FakeDownloadStream(self._objects[self._storage_key])

    async def delete_blob(self) -> None:
        if self._storage_key not in self._objects:
            raise ResourceNotFoundError(message="not found")
        del self._objects[self._storage_key]

    async def get_blob_properties(self) -> object:
        if self._storage_key not in self._objects:
            raise ResourceNotFoundError(message="not found")
        return object()


class FakeContainerClient:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.requested_keys: list[str] = []
        self.closed = False

    def get_blob_client(self, storage_key: str) -> FakeBlobClient:
        self.requested_keys.append(storage_key)
        return FakeBlobClient(self.objects, storage_key)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def container_client() -> FakeContainerClient:
    return FakeContainerClient()


@pytest.fixture
def provider(container_client: FakeContainerClient):
    azure_provider = AzureBlobStorageProvider(
        account_name="rastinaistorage",
        container_name="rastin-ai-files",
        managed_identity_client_id="11111111-1111-4111-8111-111111111111",
        container_client=container_client,
    )
    try:
        yield azure_provider
    finally:
        azure_provider.close()


def test_azure_blob_storage_saves_and_reads_binary_data(
    provider: AzureBlobStorageProvider,
) -> None:
    content = b"\x00rastin_ai\xff"

    stored = provider.save("files/file-1/content.pdf", content)

    assert stored.storage_key == "files/file-1/content.pdf"
    assert stored.size_bytes == len(content)
    assert provider.open("files/file-1/content.pdf") == content
    assert provider.read("files/file-1/content.pdf") == content


def test_azure_blob_storage_preserves_logical_storage_key(
    provider: AzureBlobStorageProvider,
    container_client: FakeContainerClient,
) -> None:
    storage_key = "files/abc123/nested/content.csv"

    provider.save(storage_key, b"a,b\n1,2\n")

    assert container_client.requested_keys == [storage_key]


def test_azure_blob_storage_exists_and_delete(
    provider: AzureBlobStorageProvider,
) -> None:
    storage_key = "files/file-1/content.txt"

    assert provider.exists(storage_key) is False
    provider.save(storage_key, b"hello")
    assert provider.exists(storage_key) is True

    provider.delete(storage_key)

    assert provider.exists(storage_key) is False


def test_azure_blob_storage_delete_missing_object_is_noop(
    provider: AzureBlobStorageProvider,
) -> None:
    provider.delete("files/missing/content.pdf")

    assert provider.exists("files/missing/content.pdf") is False


def test_azure_blob_storage_missing_object_raises_not_found(
    provider: AzureBlobStorageProvider,
) -> None:
    with pytest.raises(StorageObjectNotFoundError):
        provider.open("files/missing/content.pdf")


@pytest.mark.parametrize(
    "storage_key",
    (
        "../escape.txt",
        "files/../escape.txt",
        "/absolute/path.txt",
        r"files\windows\path.txt",
        "",
    ),
)
def test_azure_blob_storage_rejects_path_traversal_and_unsafe_keys(
    provider: AzureBlobStorageProvider,
    storage_key: str,
) -> None:
    with pytest.raises(InvalidStorageKeyError):
        provider.save(storage_key, b"nope")


@pytest.mark.parametrize(
    ("account_name", "container_name", "message"),
    (
        ("", "rastin-ai-files", "account name"),
        ("rastinaistorage", "", "container name"),
    ),
)
def test_azure_blob_storage_requires_account_and_container_config(
    account_name: str,
    container_name: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        AzureBlobStorageProvider(
            account_name=account_name,
            container_name=container_name,
            container_client=FakeContainerClient(),
        )
