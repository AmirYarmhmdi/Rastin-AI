"""File guide.

- Use: Runs an internal Azure Blob Storage smoke test.
- Usage: Run python -m rastin_ai.storage.azure_blob_smoke inside the app
  runtime.
- Duties: Verifies configured Azure Blob storage can save, read, and delete a
  temporary object without exposing credentials.
- Depends on: External packages only: standard library. Project modules:
  rastin_ai.api.dependencies, rastin_ai.core.config,
  rastin_ai.storage.azure_blob, and rastin_ai.storage.base.
"""

import asyncio
import json
import uuid
from typing import Any

from rastin_ai.api.dependencies import close_storage_providers, get_storage_provider
from rastin_ai.core.config import Settings
from rastin_ai.storage.azure_blob import AzureBlobStorageProvider
from rastin_ai.storage.base import StorageProvider

SMOKE_TEST_CONTENT = b"rastin_ai-blob-smoke-test"


class StorageSmokeTestError(RuntimeError):
    """Raised when the storage smoke test fails."""

    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__("Azure Blob storage smoke test failed.")
        self.result = result


def run_azure_blob_storage_smoke_test(
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run the smoke test against the configured Azure Blob provider."""
    resolved_settings = settings or Settings()
    if resolved_settings.STORAGE_BACKEND != "azure_blob":
        raise RuntimeError("STORAGE_BACKEND must be azure_blob for this smoke test.")

    storage_provider = get_storage_provider(resolved_settings)
    if not isinstance(storage_provider, AzureBlobStorageProvider):
        raise RuntimeError(
            "Configured storage provider is not AzureBlobStorageProvider."
        )

    return run_storage_provider_smoke_test(storage_provider)


def run_storage_provider_smoke_test(
    storage_provider: StorageProvider,
    *,
    storage_key: str | None = None,
    content: bytes = SMOKE_TEST_CONTENT,
) -> dict[str, Any]:
    """Verify save, exists, read, delete, and missing-after-delete semantics."""
    test_key = storage_key or f"smoke-tests/{uuid.uuid4()}/hello.txt"
    operations: dict[str, bool | None] = {
        "save": False,
        "exists_after_save": None,
        "read": False,
        "delete": False,
        "exists_after_delete": None,
    }
    cleanup_attempted = False
    cleanup_succeeded = False
    failure: Exception | None = None

    try:
        stored_object = storage_provider.save(test_key, content)
        operations["save"] = (
            stored_object.storage_key == test_key
            and stored_object.size_bytes == len(content)
        )
        if not operations["save"]:
            raise RuntimeError("save returned unexpected object metadata.")

        operations["exists_after_save"] = storage_provider.exists(test_key)
        if not operations["exists_after_save"]:
            raise RuntimeError("object did not exist after save.")

        operations["read"] = storage_provider.read(test_key) == content
        if not operations["read"]:
            raise RuntimeError("read content did not match expected content.")

        storage_provider.delete(test_key)
        operations["delete"] = True

        operations["exists_after_delete"] = storage_provider.exists(test_key)
        if operations["exists_after_delete"]:
            raise RuntimeError("object still existed after delete.")

        cleanup_attempted = True
        cleanup_succeeded = True
    except Exception as exc:
        failure = exc
    finally:
        if not cleanup_succeeded:
            cleanup_attempted = True
            try:
                storage_provider.delete(test_key)
                cleanup_succeeded = not storage_provider.exists(test_key)
            except Exception:
                cleanup_succeeded = False

    result: dict[str, Any] = {
        "status": "ok" if failure is None and cleanup_succeeded else "failed",
        "backend": "azure_blob",
        "content_size_bytes": len(content),
        "operations": operations,
        "cleanup": {
            "attempted": cleanup_attempted,
            "succeeded": cleanup_succeeded,
        },
    }

    if failure is not None or not cleanup_succeeded:
        raise StorageSmokeTestError(result) from failure

    return result


def main() -> None:
    try:
        result = run_azure_blob_storage_smoke_test()
    except StorageSmokeTestError as exc:
        print(json.dumps(exc.result, sort_keys=True))
        raise SystemExit(1) from exc
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "backend": "azure_blob",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(1) from exc
    finally:
        asyncio.run(close_storage_providers())

    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
