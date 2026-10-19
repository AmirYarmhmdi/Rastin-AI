"""File guide.

- Use: Contains unit tests for the internal Qdrant smoke runner.
- Usage: Run this file with pytest when checking Qdrant smoke-test behavior.
- Duties: Uses fake vector stores to verify fixed-vector operations and cleanup.
- Depends on: Project modules: rastin_ai.rag.models and
  rastin_ai.rag.qdrant_smoke.
"""

from types import SimpleNamespace

import pytest

from rastin_ai.rag.models import RetrievedChunk
from rastin_ai.rag.qdrant_smoke import (
    SMOKE_TEST_CHUNK_ID,
    SMOKE_TEST_DIMENSION,
    SMOKE_TEST_VECTOR,
    QdrantSmokeTestError,
    run_qdrant_cloud_smoke_test,
)


class FakeQdrantVectorStore:
    def __init__(
        self,
        *,
        return_expected_result: bool = True,
        fail_upsert: bool = False,
        fail_delete: bool = False,
    ) -> None:
        self.return_expected_result = return_expected_result
        self.fail_upsert = fail_upsert
        self.fail_delete = fail_delete
        self.init_kwargs: dict[str, object] = {}
        self.collection_created = False
        self.deleted = False
        self.chunks = []
        self.embeddings = []

    def ensure_collection(self) -> None:
        self.collection_created = True

    def collection_exists(self) -> bool:
        return self.collection_created and not self.deleted

    def upsert(self, chunks: list[object], embeddings: list[list[float]]) -> None:
        if self.fail_upsert:
            raise ValueError("simulated safe failure")
        self.chunks = chunks
        self.embeddings = embeddings

    def search(self, query_embedding: list[float], *, top_k: int) -> list[object]:
        if not self.return_expected_result:
            return []
        return [RetrievedChunk(chunk=self.chunks[0], score=1.0)]

    def delete_collection(self) -> None:
        if self.fail_delete:
            raise ValueError("simulated safe cleanup failure")
        self.deleted = True


def runtime_settings() -> SimpleNamespace:
    return SimpleNamespace(
        QDRANT_URL="https://qdrant.example",
        QDRANT_API_KEY="secret",
        QDRANT_COLLECTION_NAME="unused",
    )


def fake_factory(store: FakeQdrantVectorStore):
    def build_store(**kwargs) -> FakeQdrantVectorStore:
        store.init_kwargs = kwargs
        return store

    return build_store


def test_qdrant_smoke_runs_fixed_vector_workflow_and_cleans_up() -> None:
    store = FakeQdrantVectorStore()

    result = run_qdrant_cloud_smoke_test(
        runtime_settings(),
        collection_name="smoke_test_unit",
        vector_store_factory=fake_factory(store),
    )

    assert result == {
        "status": "ok",
        "backend": "qdrant_cloud",
        "operations": {
            "create_collection": True,
            "upsert": True,
            "search": True,
            "delete_collection": True,
        },
        "cleanup": {
            "attempted": True,
            "succeeded": True,
        },
    }
    assert store.init_kwargs["collection_name"] == "smoke_test_unit"
    assert store.init_kwargs["dimension"] == SMOKE_TEST_DIMENSION
    assert store.init_kwargs["ensure_collection"] is False
    assert store.init_kwargs["wait"] is True
    assert store.embeddings == [SMOKE_TEST_VECTOR]
    assert store.chunks[0].id == SMOKE_TEST_CHUNK_ID


def test_qdrant_smoke_uses_unique_temporary_collection_name() -> None:
    store = FakeQdrantVectorStore()

    run_qdrant_cloud_smoke_test(
        runtime_settings(),
        vector_store_factory=fake_factory(store),
    )

    collection_name = store.init_kwargs["collection_name"]
    assert isinstance(collection_name, str)
    assert collection_name.startswith("smoke_test_")


def test_qdrant_smoke_cleans_up_after_search_failure() -> None:
    store = FakeQdrantVectorStore(return_expected_result=False)

    with pytest.raises(QdrantSmokeTestError) as exc_info:
        run_qdrant_cloud_smoke_test(
            runtime_settings(),
            collection_name="smoke_test_unit",
            vector_store_factory=fake_factory(store),
        )

    assert exc_info.value.result["status"] == "failed"
    assert exc_info.value.result["operations"] == {
        "create_collection": True,
        "upsert": True,
        "search": False,
        "delete_collection": True,
    }
    assert exc_info.value.result["cleanup"] == {
        "attempted": True,
        "succeeded": True,
    }
    assert exc_info.value.result["error_type"] == "RuntimeError"


def test_qdrant_smoke_reports_cleanup_failure() -> None:
    store = FakeQdrantVectorStore(fail_delete=True)

    with pytest.raises(QdrantSmokeTestError) as exc_info:
        run_qdrant_cloud_smoke_test(
            runtime_settings(),
            collection_name="smoke_test_unit",
            vector_store_factory=fake_factory(store),
        )

    assert exc_info.value.result["operations"]["delete_collection"] is False
    assert exc_info.value.result["cleanup"] == {
        "attempted": True,
        "succeeded": False,
    }
    assert exc_info.value.result["error_type"] == "ValueError"


def test_qdrant_smoke_requires_runtime_config() -> None:
    settings = SimpleNamespace(
        QDRANT_URL=None,
        QDRANT_API_KEY=None,
        QDRANT_COLLECTION_NAME="unused",
    )

    with pytest.raises(QdrantSmokeTestError) as exc_info:
        run_qdrant_cloud_smoke_test(
            settings,
            collection_name="smoke_test_unit",
            vector_store_factory=fake_factory(FakeQdrantVectorStore()),
        )

    assert exc_info.value.result["cleanup"] == {
        "attempted": False,
        "succeeded": False,
    }
    assert exc_info.value.result["error_type"] == "RuntimeError"
