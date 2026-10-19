"""File guide.

- Use: Runs query embedding and vector search to retrieve matching chunks.
- Usage: Import Retriever from rastin_ai.rag.retrieval.retriever.
- Duties: Defines Retriever and related helper logic.
- Depends on: Project modules: rastin_ai.rag.embeddings.base,
  rastin_ai.rag.exceptions, rastin_ai.rag.models, and
  rastin_ai.rag.vectorstores.base.
"""

from rastin_ai.observability import observed_span, safe_update_observation
from rastin_ai.rag.embeddings.base import EmbeddingProvider
from rastin_ai.rag.exceptions import RetrieverError
from rastin_ai.rag.models import RetrievedChunk
from rastin_ai.rag.vectorstores.base import MetadataFilter, VectorStore


class Retriever:
    """Embed a query and retrieve relevant chunks from a vector store."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        filters: MetadataFilter | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            msg = "Retrieval query must not be empty."
            raise RetrieverError(msg)
        if top_k <= 0:
            msg = "top_k must be greater than zero."
            raise RetrieverError(msg)

        with observed_span(
            name="rag.retrieve",
            input={
                "top_k": top_k,
                "has_filters": bool(filters),
                "document_id": _filter_document_id(filters),
                "score_threshold": score_threshold,
            },
            metadata={"document_id": _filter_document_id(filters)},
        ) as observation:
            query_embedding = self._embedding_provider.embed_query(query)
            results = self._vector_store.search(
                query_embedding,
                top_k=top_k,
                filters=filters,
                score_threshold=score_threshold,
            )
            safe_update_observation(
                observation,
                output={"retrieved_chunk_count": len(results)},
            )
            return results


def _filter_document_id(filters: MetadataFilter | None) -> str | None:
    if not filters:
        return None
    value = filters.get("document_id")
    return str(value) if value is not None else None
