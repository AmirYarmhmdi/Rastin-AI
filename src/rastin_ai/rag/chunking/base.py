"""File guide.

- Use: Defines the text chunker contract for the RAG pipeline.
- Usage: Import TextChunker from rastin_ai.rag.chunking.base.
- Duties: Defines TextChunker and related helper logic.
- Depends on: Project modules: rastin_ai.rag.models.
"""

from typing import Protocol

from rastin_ai.rag.models import Chunk, Document


class TextChunker(Protocol):
    """Split normalized documents into stable text chunks."""

    def split(self, documents: list[Document]) -> list[Chunk]:
        """Return chunks in deterministic document and chunk order."""
