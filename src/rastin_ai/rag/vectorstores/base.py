"""File guide.

- Use: Defines the vector store contract for chunks and search results.
- Usage: Import VectorStore from rastin_ai.rag.vectorstores.base.
- Duties: Defines VectorStore and related helper logic.
- Depends on: Project modules: rastin_ai.rag.models.
"""

from typing import Any, Protocol

from rastin_ai.rag.models import Chunk, RetrievedChunk

MetadataFilter = dict[str, Any]


class VectorStore(Protocol):
    """Store and search chunk embeddings behind a vendor-neutral contract."""

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Persist chunk vectors and their retrieval payloads."""

    def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
        filters: MetadataFilter | None = None,
        score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        """Return chunks ranked by vector similarity."""

    def delete(
        self,
        *,
        chunk_ids: list[str] | None = None,
        document_id: str | None = None,
        user_id: str | None = None,
        filters: MetadataFilter | None = None,
    ) -> None:
        """Delete chunks by chunk IDs, document ID, or both."""
