"""File guide.

- Use: Runs internal Azure Blob persistence verification operations.
- Usage: Run python -m rastin_ai.storage.azure_blob_persistence inside the
  app runtime.
- Duties: Writes, reads, and deletes a deterministic persistence-test blob
  without adding a public API surface.
- Depends on: External packages only: standard library. Project modules:
  rastin_ai.api.dependencies, rastin_ai.core.config,
  rastin_ai.storage.azure_blob, and rastin_ai.storage.base.
"""

import argparse
import asyncio
import json
import re
from typing import Any, Literal

from rastin_ai.api.dependencies import close_storage_providers, get_storage_provider
from rastin_ai.core.config import Settings
from rastin_ai.storage.azure_blob import AzureBlobStorageProvider
from rastin_ai.storage.base import StorageProvider

PERSISTENCE_TEST_CONTENT = b"rastin_ai-persistence-test"
PersistenceOperation = Literal["write", "read", "delete"]
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class StoragePersistenceTestError(RuntimeError):
    """Raised when a persistence verification operation fails."""

    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__("Azure Blob persistence verification failed.")
        self.result = result


def run_azure_blob_persistence_operation(
    operation: PersistenceOperation,
    token: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run one persistence operation against the configured Azure Blob provider."""
    resolved_settings = settings or Settings()
    if resolved_settings.STORAGE_BACKEND != "azure_blob":
        raise RuntimeError(
            "STORAGE_BACKEND must be azure_blob for persistence verification."
        )

    storage_provider = get_storage_provider(resolved_settings)
    if not isinstance(storage_provider, AzureBlobStorageProvider):
        raise RuntimeError(
            "Configured storage provider is not AzureBlobStorageProvider."
        )

    return run_storage_provider_persistence_operation(
        storage_provider,
        operation=operation,
        token=token,
    )


def run_storage_provider_persistence_operation(
    storage_provider: StorageProvider,
    *,
    operation: PersistenceOperation,
    token: str,
    content: bytes = PERSISTENCE_TEST_CONTENT,
) -> dict[str, Any]:
    """Run one write, read, or delete operation for a reusable test token."""
    normalized_token = _validate_token(token)
    storage_key = _build_storage_key(normalized_token)

    if operation == "write":
        return _write_test_blob(
            storage_provider,
            token=normalized_token,
            storage_key=storage_key,
            content=content,
        )
    if operation == "read":
        return _read_test_blob(
            storage_provider,
            token=normalized_token,
            storage_key=storage_key,
            content=content,
        )
    if operation == "delete":
        return _delete_test_blob(
            storage_provider,
            token=normalized_token,
            storage_key=storage_key,
            content=content,
        )

    raise RuntimeError(f"Unsupported persistence operation: {operation}")


def _write_test_blob(
    storage_provider: StorageProvider,
    *,
    token: str,
    storage_key: str,
    content: bytes,
) -> dict[str, Any]:
    stored_object = storage_provider.save(storage_key, content)
    save_verified = (
        stored_object.storage_key == storage_key
        and stored_object.size_bytes == len(content)
    )
    exists_after_write = storage_provider.exists(storage_key)
    result = _base_result(
        operation="write",
        token=token,
        content=content,
        verified={
            "save": save_verified,
            "exists_after_write": exists_after_write,
        },
    )

    if not save_verified or not exists_after_write:
        result["status"] = "failed"
        raise StoragePersistenceTestError(result)

    return result


def _read_test_blob(
    storage_provider: StorageProvider,
    *,
    token: str,
    storage_key: str,
    content: bytes,
) -> dict[str, Any]:
    exists_before_read = storage_provider.exists(storage_key)
    read_verified = exists_before_read and storage_provider.read(storage_key) == content
    result = _base_result(
        operation="read",
        token=token,
        content=content,
        verified={
            "exists_before_read": exists_before_read,
            "read": read_verified,
        },
    )

    if not exists_before_read or not read_verified:
        result["status"] = "failed"
        raise StoragePersistenceTestError(result)

    return result


def _delete_test_blob(
    storage_provider: StorageProvider,
    *,
    token: str,
    storage_key: str,
    content: bytes,
) -> dict[str, Any]:
    storage_provider.delete(storage_key)
    exists_after_delete = storage_provider.exists(storage_key)
    result = _base_result(
        operation="delete",
        token=token,
        content=content,
        verified={
            "delete": True,
            "exists_after_delete": exists_after_delete,
        },
    )

    if exists_after_delete:
        result["status"] = "failed"
        raise StoragePersistenceTestError(result)

    return result


def _base_result(
    *,
    operation: PersistenceOperation,
    token: str,
    content: bytes,
    verified: dict[str, bool],
) -> dict[str, Any]:
    return {
        "status": "ok",
        "backend": "azure_blob",
        "operation": operation,
        "token": token,
        "content_size_bytes": len(content),
        "verified": verified,
    }


def _build_storage_key(token: str) -> str:
    return f"persistence-tests/{token}/hello.txt"


def _validate_token(token: str) -> str:
    normalized_token = token.strip()
    if normalized_token != token or not _TOKEN_PATTERN.fullmatch(normalized_token):
        raise ValueError(
            "Token must be 1-128 characters and contain only letters, digits, "
            "periods, underscores, or hyphens."
        )
    return normalized_token


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m rastin_ai.storage.azure_blob_persistence"
    )
    parser.add_argument("operation", choices=("write", "read", "delete"))
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    try:
        result = run_azure_blob_persistence_operation(
            operation=args.operation,
            token=args.token,
        )
    except StoragePersistenceTestError as exc:
        print(json.dumps(exc.result, sort_keys=True))
        raise SystemExit(1) from exc
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "backend": "azure_blob",
                    "operation": args.operation,
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
