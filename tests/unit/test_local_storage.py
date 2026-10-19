"""File guide.

- Use: Contains unit tests for local storage behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.storage.exceptions, and
  rastin_ai.storage.local.
"""

import pytest

from rastin_ai.storage.exceptions import (
    InvalidStorageKeyError,
    StorageObjectNotFoundError,
)
from rastin_ai.storage.local import LocalStorageProvider


def test_local_storage_saves_and_reads_binary_data(tmp_path) -> None:
    provider = LocalStorageProvider(tmp_path)
    content = b"\x00rastin_ai\xff"

    stored = provider.save("files/file-1/content.pdf", content)

    assert stored.storage_key == "files/file-1/content.pdf"
    assert stored.size_bytes == len(content)
    assert provider.open("files/file-1/content.pdf") == content
    assert provider.read("files/file-1/content.pdf") == content


def test_local_storage_exists_and_delete(tmp_path) -> None:
    provider = LocalStorageProvider(tmp_path)
    storage_key = "files/file-1/content.txt"

    assert provider.exists(storage_key) is False
    provider.save(storage_key, b"hello")
    assert provider.exists(storage_key) is True

    provider.delete(storage_key)

    assert provider.exists(storage_key) is False


def test_local_storage_supports_nested_generated_keys(tmp_path) -> None:
    provider = LocalStorageProvider(tmp_path)

    provider.save("files/abc123/nested/content.csv", b"a,b\n1,2\n")

    assert provider.open("files/abc123/nested/content.csv") == b"a,b\n1,2\n"


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
def test_local_storage_rejects_path_traversal_and_unsafe_keys(
    tmp_path,
    storage_key,
) -> None:
    provider = LocalStorageProvider(tmp_path)

    with pytest.raises(InvalidStorageKeyError):
        provider.save(storage_key, b"nope")


def test_local_storage_missing_object_raises_not_found(tmp_path) -> None:
    provider = LocalStorageProvider(tmp_path)

    with pytest.raises(StorageObjectNotFoundError):
        provider.open("files/missing/content.pdf")
