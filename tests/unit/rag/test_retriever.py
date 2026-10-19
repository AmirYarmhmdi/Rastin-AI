"""File guide.

- Use: Contains unit tests for retriever behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.rag.models, and
  rastin_ai.rag.retrieval.retriever.
"""

from rastin_ai.rag.models import Chunk, RetrievedChunk
from rastin_ai.rag.retrieval.retriever import Retriever


class FakeEmbeddingProvider:
    dimension = 2

    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.2, 0.8]


class FakeVectorStore:
    def __init__(self) -> None:
        self.search_call: dict[str, object] | None = None

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        pass

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
        filters: dict[str, object] | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        self.search_call = {
            "query_embedding": query_embedding,
            "top_k": top_k,
            "filters": filters,
            "score_threshold": score_threshold,
        }
        return [
            RetrievedChunk(
                chunk=Chunk(
                    id="chunk-1",
                    document_id="doc-1",
                    text="answer",
                    chunk_index=0,
                    token_count=1,
                ),
                score=0.9,
            )
        ]

    def delete(
        self,
        *,
        chunk_ids: list[str] | None = None,
        document_id: str | None = None,
    ) -> None:
        pass


def test_retriever_embeds_query_and_forwards_search_options() -> None:
    embedder = FakeEmbeddingProvider()
    vector_store = FakeVectorStore()
    retriever = Retriever(embedding_provider=embedder, vector_store=vector_store)

    results = retriever.retrieve(
        "What matters?",
        top_k=3,
        filters={"project_id": "project-1"},
        score_threshold=0.75,
    )

    assert embedder.queries == ["What matters?"]
    assert vector_store.search_call == {
        "query_embedding": [0.2, 0.8],
        "top_k": 3,
        "filters": {"project_id": "project-1"},
        "score_threshold": 0.75,
    }
    assert isinstance(results[0], RetrievedChunk)
