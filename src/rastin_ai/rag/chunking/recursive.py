"""File guide.

- Use: Splits documents into stable overlapping text chunks.
- Usage: Import RecursiveChunkerConfig, and RecursiveTextChunker from
  rastin_ai.rag.chunking.recursive.
- Duties: Defines RecursiveChunkerConfig, and RecursiveTextChunker and related
  helper logic.
- Depends on: Project modules: rastin_ai.rag.models.
"""

import hashlib
import logging

from pydantic import BaseModel, Field, model_validator

from rastin_ai.rag.models import Chunk, Document

logger = logging.getLogger(__name__)


class RecursiveChunkerConfig(BaseModel):
    """Configuration for deterministic token-aware chunking."""

    chunk_size: int = Field(default=800, ge=1)
    chunk_overlap: int = Field(default=100, ge=0)

    @model_validator(mode="after")
    def validate_overlap(self) -> "RecursiveChunkerConfig":
        # Overlap must leave room for the chunk window to move forward.
        if self.chunk_overlap >= self.chunk_size:
            msg = "chunk_overlap must be smaller than chunk_size."
            raise ValueError(msg)
        return self


class RecursiveTextChunker:
    """Split documents into stable, overlapping whitespace-token chunks."""

    def __init__(
        self,
        *,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> None:
        self.config = RecursiveChunkerConfig(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def split(self, documents: list[Document]) -> list[Chunk]:
        chunks: list[Chunk] = []

        for document in documents:
            for chunk_index, text in enumerate(self._split_text(document.text)):
                # Keep source metadata on every chunk for later retrieval context.
                metadata = {
                    **document.metadata,
                    "document_id": document.id,
                    "source": document.source,
                    "chunk_index": chunk_index,
                }
                chunks.append(
                    Chunk(
                        id=self._chunk_id(document.id, chunk_index, text),
                        document_id=document.id,
                        text=text,
                        chunk_index=chunk_index,
                        metadata=metadata,
                        token_count=self._count_tokens(text),
                    )
                )

        logger.info(
            "Chunking completed",
            extra={
                "document_count": len(documents),
                "chunk_count": len(chunks),
                "chunk_size": self.config.chunk_size,
                "chunk_overlap": self.config.chunk_overlap,
            },
        )
        return chunks

    def _split_text(self, text: str) -> list[str]:
        # Whitespace tokens keep v1 chunking simple and deterministic.
        words = text.split()
        if not words:
            return []

        chunks: list[str] = []
        start = 0
        step = self.config.chunk_size - self.config.chunk_overlap

        while start < len(words):
            end = min(start + self.config.chunk_size, len(words))
            chunk = " ".join(words[start:end]).strip()
            if chunk:
                chunks.append(chunk)
            if end == len(words):
                break
            # Move by less than chunk_size when overlap is configured.
            start += step

        return chunks

    @staticmethod
    def _count_tokens(text: str) -> int:
        return len(text.split())

    @staticmethod
    def _chunk_id(document_id: str, chunk_index: int, text: str) -> str:
        # Hash the stable chunk inputs so re-indexing creates the same IDs.
        digest = hashlib.sha256(
            f"{document_id}:{chunk_index}:{text}".encode(),
        ).hexdigest()
        return f"chunk_{digest[:24]}"
