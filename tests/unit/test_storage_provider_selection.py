"""File guide.

- Use: Contains unit tests for storage provider dependency selection.
- Usage: Run this file with pytest when checking storage backend wiring.
- Duties: Builds settings and fake providers to check explicit backend behavior.
- Depends on: External packages only: pytest. Project modules:
  rastin_ai.api.dependencies, rastin_ai.core.config, and
  rastin_ai.storage.local.
"""

from types import SimpleNamespace

import pytest
from helpers import clear_settings_env

from rastin_ai.api import dependencies
from rastin_ai.core.config import Settings
from rastin_ai.storage.local import LocalStorageProvider


class FakeAzureBlobStorageProvider:
    def __init__(
        self,
        *,
        account_name: str,
        container_name: str,
        managed_identity_client_id: str | None,
    ) -> None:
        self.account_name = account_name
        self.container_name = container_name
        self.managed_identity_client_id = managed_identity_client_id


@pytest.fixture(autouse=True)
def clear_storage_provider_caches():
    dependencies._get_local_storage_provider.cache_clear()
    dependencies._get_azure_blob_storage_provider.cache_clear()
    dependencies._azure_blob_storage_providers.clear()
    yield
    dependencies._get_local_storage_provider.cache_clear()
    dependencies._get_azure_blob_storage_provider.cache_clear()
    dependencies._azure_blob_storage_providers.clear()


def test_get_storage_provider_selects_local(monkeypatch, tmp_path) -> None:
    clear_settings_env(monkeypatch)
    settings = Settings(LOCAL_STORAGE_ROOT=str(tmp_path))

    provider = dependencies.get_storage_provider(settings)

    assert isinstance(provider, LocalStorageProvider)


def test_get_storage_provider_selects_azure_blob(monkeypatch) -> None:
    clear_settings_env(monkeypatch)
    monkeypatch.setattr(
        dependencies,
        "AzureBlobStorageProvider",
        FakeAzureBlobStorageProvider,
    )
    settings = Settings(
        STORAGE_BACKEND="azure_blob",
        AZURE_STORAGE_ACCOUNT_NAME=" rastinaistorage ",
        AZURE_STORAGE_CONTAINER_NAME=" rastin-ai-files ",
        AZURE_STORAGE_MANAGED_IDENTITY_CLIENT_ID=(
            "11111111-1111-4111-8111-111111111111"
        ),
    )

    provider = dependencies.get_storage_provider(settings)

    assert isinstance(provider, FakeAzureBlobStorageProvider)
    assert provider.account_name == "rastinaistorage"
    assert provider.container_name == "rastin-ai-files"
    assert provider.managed_identity_client_id == "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize(
    "missing_setting",
    ("AZURE_STORAGE_ACCOUNT_NAME", "AZURE_STORAGE_CONTAINER_NAME"),
)
def test_get_storage_provider_requires_azure_blob_config(
    monkeypatch,
    missing_setting: str,
) -> None:
    clear_settings_env(monkeypatch)
    values = {
        "STORAGE_BACKEND": "azure_blob",
        "AZURE_STORAGE_ACCOUNT_NAME": "rastinaistorage",
        "AZURE_STORAGE_CONTAINER_NAME": "rastin-ai-files",
    }
    values[missing_setting] = None
    settings = Settings(**values)

    with pytest.raises(RuntimeError, match=missing_setting):
        dependencies.get_storage_provider(settings)


def test_get_storage_provider_rejects_unsupported_backend() -> None:
    settings = SimpleNamespace(
        STORAGE_BACKEND="s3",
        LOCAL_STORAGE_ROOT="storage",
    )

    with pytest.raises(RuntimeError, match="STORAGE_BACKEND must be one of"):
        dependencies.get_storage_provider(settings)
