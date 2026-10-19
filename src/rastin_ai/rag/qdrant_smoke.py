"""File guide.

- Use: Runs an internal Qdrant Cloud vector workflow smoke test.
- Usage: Run python -m rastin_ai.rag.qdrant_smoke inside the app runtime.
- Duties: Verifies configured Qdrant can create, write, search, and clean up a
  temporary collection without generating embeddings or exposing credentials.
- Depends on: External packages only: standard library. Project modules:
  rastin_ai.core.config, rastin_ai.rag.models, and
  rastin_ai.rag.vectorstores.qdrant.
"""

import json
import uuid
from collections.abc import Callable
from typing import Any

from rastin_ai.core.config import Settings
from rastin_ai.rag.models import Chunk
from rastin_ai.rag.vectorstores.qdrant import QdrantVectorStore

SMOKE_TEST_DIMENSION = 4
SMOKE_TEST_VECTOR = [0.1, 0.2, 0.3, 0.4]
SMOKE_TEST_CHUNK_ID = "qdrant-smoke-chunk"
SMOKE_TEST_DOCUMENT_ID = "qdrant-smoke-document"

VectorStoreFactory = Callable[..., QdrantVectorStore]


class QdrantSmokeTestError(RuntimeError):
    """Raised when the Qdrant smoke test fails."""

    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__("Qdrant smoke test failed.")
        self.result = result


def run_qdrant_cloud_smoke_test(
    settings: Settings | None = None,
    *,
    collection_name: str | None = None,
    vector_store_factory: VectorStoreFactory = QdrantVectorStore,
) -> dict[str, Any]:
    """Run a fixed-vector create/upsert/search/delete workflow against Qdrant."""
    resolved_settings = settings or Settings()
    test_collection = collection_name or f"smoke_test_{uuid.uuid4().hex}"
    operations = {
        "create_collection": False,
        "upsert": False,
        "search": False,
        "delete_collection": False,
    }
    cleanup = {
        "attempted": False,
        "succeeded": False,
    }
    result: dict[str, Any] = {
        "status": "failed",
        "backend": "qdrant_cloud",
        "operations": operations,
        "cleanup": cleanup,
    }
    vector_store: QdrantVectorStore | None = None
    failure: Exception | None = None

    try:
        _validate_runtime_config(resolved_settings)
        vector_store = vector_store_factory(
            collection_name=test_collection,
            dimension=SMOKE_TEST_DIMENSION,
            settings=resolved_settings,
            ensure_collection=False,
            wait=True,
        )
        vector_store.ensure_collection()
        operations["create_collection"] = vector_store.collection_exists()
        if not operations["create_collection"]:
            raise RuntimeError("Qdrant smoke collection was not created.")

        vector_store.upsert([_smoke_chunk()], [SMOKE_TEST_VECTOR])
        operations["upsert"] = True

        results = vector_store.search(SMOKE_TEST_VECTOR, top_k=1)
        operations["search"] = (
            bool(results) and results[0].chunk.id == SMOKE_TEST_CHUNK_ID
        )
        if not operations["search"]:
            raise RuntimeError("Qdrant smoke point was not returned by search.")
    except Exception as exc:
        failure = exc
    finally:
        if vector_store is not None:
            cleanup["attempted"] = True
            try:
                vector_store.delete_collection()
                operations["delete_collection"] = True
                cleanup["succeeded"] = not vector_store.collection_exists()
            except Exception as exc:
                cleanup["succeeded"] = False
                if failure is None:
                    failure = exc

    if failure is not None or not cleanup["succeeded"]:
        result["error_type"] = type(failure).__name__ if failure is not None else None
        raise QdrantSmokeTestError(result) from failure

    result["status"] = "ok"
    return result


def _validate_runtime_config(settings: Settings) -> None:
    if not settings.QDRANT_URL:
        raise RuntimeError("QDRANT_URL must be set for the Qdrant smoke test.")
    if not settings.QDRANT_API_KEY:
        raise RuntimeError("QDRANT_API_KEY must be set for the Qdrant smoke test.")


def _smoke_chunk() -> Chunk:
    return Chunk(
        id=SMOKE_TEST_CHUNK_ID,
        document_id=SMOKE_TEST_DOCUMENT_ID,
        text="Rastin-AI Qdrant smoke test chunk.",
        chunk_index=0,
        metadata={"source": "qdrant_smoke"},
        token_count=5,
    )


def main() -> None:
    try:
        result = run_qdrant_cloud_smoke_test()
    except QdrantSmokeTestError as exc:
        print(json.dumps(exc.result, sort_keys=True))
        raise SystemExit(1) from exc
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "backend": "qdrant_cloud",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(1) from exc

    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
