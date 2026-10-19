"""File guide.

- Use: Stores uploaded files in Azure Blob Storage.
- Usage: Import AzureBlobStorageProvider from rastin_ai.storage.azure_blob.
- Duties: Defines AzureBlobStorageProvider and Azure Blob helper logic.
- Depends on: External packages: azure-core, azure-identity, and
  azure-storage-blob. Project modules: rastin_ai.storage.base, and
  rastin_ai.storage.exceptions.
"""

import asyncio
import threading
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from typing import TypeVar

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.identity.aio import ManagedIdentityCredential
from azure.storage.blob.aio import ContainerClient

from rastin_ai.storage.base import StoredObject
from rastin_ai.storage.exceptions import (
    InvalidStorageKeyError,
    StorageError,
    StorageObjectNotFoundError,
)

_T = TypeVar("_T")


class _AsyncRunner:
    """Run Azure async SDK calls on one reusable event loop."""

    def __init__(self) -> None:
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait()

    def run(self, operation_factory: Callable[[], Awaitable[_T]]) -> _T:
        future = asyncio.run_coroutine_threadsafe(
            operation_factory(),
            self._loop,
        )
        return future.result()

    def close(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()
        self._loop.close()


class AzureBlobStorageProvider:
    """Store objects in Azure Blob Storage behind logical storage keys."""

    def __init__(
        self,
        *,
        account_name: str,
        container_name: str,
        managed_identity_client_id: str | None = None,
        container_client: ContainerClient | None = None,
    ) -> None:
        self._account_name = self._require_config_value(
            account_name,
            "Azure storage account name is required.",
        )
        self._container_name = self._require_config_value(
            container_name,
            "Azure storage container name is required.",
        )
        self._runner = _AsyncRunner()
        self._credential: ManagedIdentityCredential | None = None
        self._closed = False

        if container_client is None:
            self._credential = ManagedIdentityCredential(
                client_id=managed_identity_client_id,
            )
            account_url = f"https://{self._account_name}.blob.core.windows.net"
            self._container_client = ContainerClient(
                account_url=account_url,
                container_name=self._container_name,
                credential=self._credential,
            )
        else:
            self._container_client = container_client

    def save(self, storage_key: str, content: bytes) -> StoredObject:
        self._validate_storage_key(storage_key)

        try:
            self._runner.run(lambda: self._upload_blob(storage_key, content))
        except AzureError as exc:
            msg = f"Could not save storage object: {storage_key}"
            raise StorageError(msg) from exc

        return StoredObject(storage_key=storage_key, size_bytes=len(content))

    def open(self, storage_key: str) -> bytes:
        self._validate_storage_key(storage_key)

        try:
            return self._runner.run(lambda: self._download_blob(storage_key))
        except ResourceNotFoundError as exc:
            msg = f"Storage object does not exist: {storage_key}"
            raise StorageObjectNotFoundError(msg) from exc
        except AzureError as exc:
            msg = f"Could not read storage object: {storage_key}"
            raise StorageError(msg) from exc

    def read(self, storage_key: str) -> bytes:
        return self.open(storage_key)

    def delete(self, storage_key: str) -> None:
        self._validate_storage_key(storage_key)

        try:
            self._runner.run(lambda: self._delete_blob(storage_key))
        except ResourceNotFoundError:
            return
        except AzureError as exc:
            msg = f"Could not delete storage object: {storage_key}"
            raise StorageError(msg) from exc

    def exists(self, storage_key: str) -> bool:
        self._validate_storage_key(storage_key)

        try:
            self._runner.run(lambda: self._get_blob_properties(storage_key))
        except ResourceNotFoundError:
            return False
        except AzureError as exc:
            msg = f"Could not check storage object existence: {storage_key}"
            raise StorageError(msg) from exc

        return True

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        self._runner.run(self._close_clients)
        self._runner.close()

    async def aclose(self) -> None:
        await asyncio.to_thread(self.close)

    async def _upload_blob(self, storage_key: str, content: bytes) -> None:
        blob_client = self._container_client.get_blob_client(storage_key)
        await blob_client.upload_blob(content, overwrite=True)

    async def _download_blob(self, storage_key: str) -> bytes:
        blob_client = self._container_client.get_blob_client(storage_key)
        download_stream = await blob_client.download_blob()
        return await download_stream.readall()

    async def _delete_blob(self, storage_key: str) -> None:
        blob_client = self._container_client.get_blob_client(storage_key)
        await blob_client.delete_blob()

    async def _get_blob_properties(self, storage_key: str) -> None:
        blob_client = self._container_client.get_blob_client(storage_key)
        await blob_client.get_blob_properties()

    async def _close_clients(self) -> None:
        await self._container_client.close()
        if self._credential is not None:
            await self._credential.close()

    @staticmethod
    def _require_config_value(value: str, message: str) -> str:
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError(message)
        return normalized_value

    @staticmethod
    def _validate_storage_key(storage_key: str) -> None:
        if not storage_key:
            msg = "Storage key must not be empty."
            raise InvalidStorageKeyError(msg)
        if "\x00" in storage_key:
            msg = "Storage key must not contain null bytes."
            raise InvalidStorageKeyError(msg)
        if "\\" in storage_key:
            msg = "Storage key must use forward slashes."
            raise InvalidStorageKeyError(msg)

        logical_path = PurePosixPath(storage_key)
        if logical_path.is_absolute():
            msg = "Storage key must be relative."
            raise InvalidStorageKeyError(msg)
        if any(part in {"", ".", ".."} for part in logical_path.parts):
            msg = "Storage key must not contain traversal segments."
            raise InvalidStorageKeyError(msg)
