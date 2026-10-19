"""File guide.

- Use: Exports storage provider contracts and implementations.
- Usage: Import from rastin_ai.storage.__init__ to use the package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules: rastin_ai.storage.azure_blob,
  rastin_ai.storage.base, and rastin_ai.storage.local.
"""

from rastin_ai.storage.azure_blob import AzureBlobStorageProvider
from rastin_ai.storage.base import StorageProvider, StoredObject
from rastin_ai.storage.local import LocalStorageProvider

__all__ = [
    "AzureBlobStorageProvider",
    "LocalStorageProvider",
    "StorageProvider",
    "StoredObject",
]
