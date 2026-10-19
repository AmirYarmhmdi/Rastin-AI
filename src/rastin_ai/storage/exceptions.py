"""File guide.

- Use: Defines storage-layer errors for providers and services.
- Usage: Import InvalidStorageKeyError, StorageError, and StorageObjectNotFoundError
  from rastin_ai.storage.exceptions.
- Duties: Defines InvalidStorageKeyError, StorageError, and
  StorageObjectNotFoundError and related helper logic.
- Depends on: No direct project module dependencies.
"""


class StorageError(Exception):
    """Base error for storage provider failures."""


class InvalidStorageKeyError(StorageError):
    """Raised when a logical storage key is unsafe or invalid."""


class StorageObjectNotFoundError(StorageError):
    """Raised when a requested storage object does not exist."""
