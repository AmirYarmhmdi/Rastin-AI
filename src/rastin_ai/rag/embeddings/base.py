"""File guide.

- Use: Defines the embedding provider contract for the RAG pipeline.
- Usage: Import EmbeddingProvider from rastin_ai.rag.embeddings.base.
- Duties: Defines EmbeddingProvider and related helper logic.
- Depends on: External packages only: typing.
"""

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Generate vector embeddings without leaking vendor SDK types."""

    @property
    def dimension(self) -> int:
        """Return the provider's configured vector dimension."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed document chunks in order."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a retrieval query."""
