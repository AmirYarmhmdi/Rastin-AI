"""File guide.

- Use: Contains unit tests for qdrant vectorstore behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.rag.exceptions, rastin_ai.rag.models,
  and rastin_ai.rag.vectorstores.qdrant.
"""

from types import SimpleNamespace

import pytest

from rastin_ai.rag.exceptions import VectorStoreError
from rastin_ai.rag.models import Chunk, RetrievedChunk
from rastin_ai.rag.vectorstores.qdrant import QdrantVectorStore


class FakeModels:
    class Distance:
        COSINE = "Cosine"

    class VectorParams:
        def __init__(self, *, size: int, distance: str) -> None:
            self.size = size
            self.distance = distance

    class PointStruct:
        def __init__(self, *, id: str, vector: list[float], payload: dict) -> None:
            self.id = id
            self.vector = vector
            self.payload = payload

    class MatchValue:
        def __init__(self, *, value: object) -> None:
            self.value = value

    class FieldCondition:
        def __init__(self, *, key: str, match: object) -> None:
            self.key = key
            self.match = match

    class Filter:
        def __init__(self, *, must: list[object]) -> None:
            self.must = must

    class PointIdsList:
        def __init__(self, *, points: list[str]) -> None:
            self.points = points

    class FilterSelector:
        def __init__(self, *, filter: object) -> None:
            self.filter = filter


class FakeQdrantClient:
    def __init__(self, *, collection_exists: bool = True) -> None:
        self._collection_exists = collection_exists
        self.created_collections: list[dict[str, object]] = []
        self.upserts: list[dict[str, object]] = []
        self.searches: list[dict[str, object]] = []
        self.deletes: list[dict[str, object]] = []
        self.deleted_collections: list[str] = []
        self.search_points = [
            SimpleNamespace(
                id="point-1",
                score=0.88,
                payload={
                    "chunk_id": "chunk-1",
                    "document_id": "doc-1",
                    "text": "retrieved text",
                    "chunk_index": 2,
                    "metadata": {
                        "user_id": "user-1",
                        "filename": "report.pdf",
                        "page_number": 4,
                        "token_count": 2,
                    },
                },
            )
        ]

    def collection_exists(self, collection_name: str) -> bool:
        return self._collection_exists

    def create_collection(
        self,
        *,
        collection_name: str,
        vectors_config: object,
    ) -> None:
        self.created_collections.append(
            {"collection_name": collection_name, "vectors_config": vectors_config}
        )

    def get_collection(self, collection_name: str) -> object:
        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(vectors=SimpleNamespace(size=2))
            )
        )

    def upsert(
        self,
        *,
        collection_name: str,
        points: list[object],
        wait: bool | None = None,
    ) -> None:
        self.upserts.append(
            {"collection_name": collection_name, "points": points, "wait": wait}
        )

    def search(self, **kwargs) -> list[object]:
        self.searches.append(kwargs)
        return self.search_points

    def delete(self, *, collection_name: str, points_selector: object) -> None:
        self.deletes.append(
            {"collection_name": collection_name, "points_selector": points_selector}
        )

    def delete_collection(self, *, collection_name: str) -> None:
        self.deleted_collections.append(collection_name)
        self._collection_exists = False


def qdrant_store(client: FakeQdrantClient | None = None) -> QdrantVectorStore:
    store = QdrantVectorStore(
        collection_name="test_chunks",
        dimension=2,
        client=client or FakeQdrantClient(),
        ensure_collection=False,
    )
    store._models = FakeModels
    return store


def qdrant_store_with_wait(client: FakeQdrantClient | None = None) -> QdrantVectorStore:
    store = QdrantVectorStore(
        collection_name="test_chunks",
        dimension=2,
        client=client or FakeQdrantClient(),
        ensure_collection=False,
        wait=True,
    )
    store._models = FakeModels
    return store


def sample_chunk() -> Chunk:
    return Chunk(
        id="chunk-1",
        document_id="doc-1",
        text="hello world",
        chunk_index=0,
        metadata={
            "source": "/tmp/report.pdf",
            "user_id": "user-1",
            "organization_id": "org-1",
            "project_id": "project-1",
            "document_scope": "PROJECT_LIBRARY",
            "uploaded_by_user_id": "user-1",
            "filename": "report.pdf",
            "page_number": 1,
            "source_location": "page:1",
            "location_type": "page",
        },
        token_count=2,
    )


def test_qdrant_store_creates_missing_collection() -> None:
    client = FakeQdrantClient(collection_exists=False)
    store = qdrant_store(client)

    store.ensure_collection()

    created = client.created_collections[0]
    assert created["collection_name"] == "test_chunks"
    assert created["vectors_config"].size == 2
    assert created["vectors_config"].distance == "Cosine"


def test_qdrant_store_validates_existing_collection_dimension() -> None:
    store = qdrant_store(FakeQdrantClient(collection_exists=True))

    store.ensure_collection()


def test_qdrant_store_upsert_builds_payload() -> None:
    client = FakeQdrantClient()
    store = qdrant_store(client)

    store.upsert([sample_chunk()], [[0.1, 0.2]])

    point = client.upserts[0]["points"][0]
    assert point.vector == [0.1, 0.2]
    assert point.payload["chunk_id"] == "chunk-1"
    assert point.payload["document_id"] == "doc-1"
    assert point.payload["user_id"] == "user-1"
    assert point.payload["organization_id"] == "org-1"
    assert point.payload["project_id"] == "project-1"
    assert point.payload["document_scope"] == "PROJECT_LIBRARY"
    assert point.payload["uploaded_by_user_id"] == "user-1"
    assert point.payload["text"] == "hello world"
    assert point.payload["metadata"]["page_number"] == 1
    assert point.payload["metadata"]["source_location"] == "page:1"
    assert point.payload["metadata"]["location_type"] == "page"
    assert client.upserts[0]["wait"] is None


def test_qdrant_store_can_wait_for_upsert() -> None:
    client = FakeQdrantClient()
    store = qdrant_store_with_wait(client)

    store.upsert([sample_chunk()], [[0.1, 0.2]])

    assert client.upserts[0]["wait"] is True


def test_qdrant_store_rejects_embedding_dimension_mismatch() -> None:
    store = qdrant_store()

    with pytest.raises(VectorStoreError, match="dimension mismatch"):
        store.upsert([sample_chunk()], [[0.1]])


def test_qdrant_store_search_maps_results_and_filters() -> None:
    client = FakeQdrantClient()
    store = qdrant_store(client)

    results = store.search(
        [0.1, 0.2],
        top_k=3,
        filters={
            "project_id": "project-1",
            "organization_id": "org-1",
            "document_scope": "PROJECT_LIBRARY",
            "document_id": "doc-1",
        },
        score_threshold=0.5,
    )

    assert isinstance(results[0], RetrievedChunk)
    assert results[0].chunk.id == "chunk-1"
    assert results[0].chunk.metadata["page_number"] == 4
    search_call = client.searches[0]
    assert search_call["limit"] == 3
    assert search_call["score_threshold"] == 0.5
    filter_keys = [condition.key for condition in search_call["query_filter"].must]
    assert filter_keys == [
        "project_id",
        "organization_id",
        "document_scope",
        "document_id",
    ]


def test_qdrant_store_rejects_document_search_without_user_filter() -> None:
    store = qdrant_store()

    with pytest.raises(VectorStoreError, match="requires user_id or organization_id"):
        store.search([0.1, 0.2], top_k=3, filters={"document_id": "doc-1"})


def test_qdrant_store_delete_by_chunk_ids_and_document_id() -> None:
    client = FakeQdrantClient()
    store = qdrant_store(client)

    store.delete(chunk_ids=["chunk-1"], document_id="doc-1", user_id="user-1")

    assert len(client.deletes) == 2
    assert client.deletes[0]["points_selector"].points
    filter_keys = [
        condition.key for condition in client.deletes[1]["points_selector"].filter.must
    ]
    assert filter_keys == ["document_id", "user_id"]


def test_qdrant_store_delete_supports_project_scoped_document_filter() -> None:
    client = FakeQdrantClient()
    store = qdrant_store(client)

    store.delete(
        document_id="doc-1",
        filters={
            "organization_id": "org-1",
            "project_id": "project-1",
            "document_scope": "CHAT_ATTACHMENT",
            "session_id": "session-1",
        },
    )

    filter_keys = [
        condition.key for condition in client.deletes[0]["points_selector"].filter.must
    ]
    assert filter_keys == [
        "organization_id",
        "project_id",
        "document_scope",
        "session_id",
        "document_id",
    ]


def test_qdrant_store_deletes_collection_when_it_exists() -> None:
    client = FakeQdrantClient(collection_exists=True)
    store = qdrant_store(client)

    store.delete_collection()

    assert client.deleted_collections == ["test_chunks"]
    assert store.collection_exists() is False
