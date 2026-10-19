"""File guide.

- Use: Defines the storage provider contract used by upload services.
- Usage: Import StorageProvider, and StoredObject from rastin_ai.storage.base.
- Duties: Defines StorageProvider, and StoredObject and related helper logic.
- Depends on: External packages only: dataclasses, and typing.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    """Information returned after storing an object."""

    storage_key: str
    size_bytes: int


class StorageProvider(Protocol):
    """Backend-neutral object storage contract."""

    def save(self, storage_key: str, content: bytes) -> StoredObject:
        """Store binary content under a logical storage key."""

    def open(self, storage_key: str) -> bytes:
        """Read binary content stored under a logical storage key."""

    def read(self, storage_key: str) -> bytes:
        """Read binary content stored under a logical storage key."""

    def delete(self, storage_key: str) -> None:
        """Delete an object by logical storage key."""

    def exists(self, storage_key: str) -> bool:
        """Return whether an object exists for the logical storage key."""
