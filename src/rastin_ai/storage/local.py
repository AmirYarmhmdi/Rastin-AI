"""File guide.

- Use: Stores uploaded files on the local filesystem.
- Usage: Import LocalStorageProvider from rastin_ai.storage.local.
- Duties: Defines LocalStorageProvider and related helper logic.
- Depends on: Project modules: rastin_ai.storage.base, and
  rastin_ai.storage.exceptions.
"""

from pathlib import Path, PurePosixPath

from rastin_ai.storage.base import StoredObject
from rastin_ai.storage.exceptions import (
    InvalidStorageKeyError,
    StorageError,
    StorageObjectNotFoundError,
)


class LocalStorageProvider:
    """Store objects on the local filesystem behind logical storage keys."""

    def __init__(self, storage_root: str | Path) -> None:
        self._storage_root = Path(storage_root).expanduser().resolve()

    def save(self, storage_key: str, content: bytes) -> StoredObject:
        target_path = self._resolve_storage_key(storage_key)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(content)
        except OSError as exc:
            msg = f"Could not save storage object: {storage_key}"
            raise StorageError(msg) from exc

        return StoredObject(storage_key=storage_key, size_bytes=len(content))

    def open(self, storage_key: str) -> bytes:
        target_path = self._resolve_storage_key(storage_key)
        if not target_path.is_file():
            msg = f"Storage object does not exist: {storage_key}"
            raise StorageObjectNotFoundError(msg)

        try:
            return target_path.read_bytes()
        except OSError as exc:
            msg = f"Could not read storage object: {storage_key}"
            raise StorageError(msg) from exc

    def read(self, storage_key: str) -> bytes:
        return self.open(storage_key)

    def delete(self, storage_key: str) -> None:
        target_path = self._resolve_storage_key(storage_key)
        try:
            target_path.unlink(missing_ok=True)
        except OSError as exc:
            msg = f"Could not delete storage object: {storage_key}"
            raise StorageError(msg) from exc

    def exists(self, storage_key: str) -> bool:
        target_path = self._resolve_storage_key(storage_key)
        return target_path.is_file()

    def _resolve_storage_key(self, storage_key: str) -> Path:
        self._validate_storage_key(storage_key)
        logical_path = PurePosixPath(storage_key)
        target_path = self._storage_root.joinpath(*logical_path.parts).resolve()

        try:
            target_path.relative_to(self._storage_root)
        except ValueError as exc:
            msg = f"Storage key escapes storage root: {storage_key}"
            raise InvalidStorageKeyError(msg) from exc

        return target_path

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
