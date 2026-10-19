"""File guide.

- Use: Indexes documents by loading, chunking, embedding, and storing chunks.
- Usage: Import DocumentIndexer from rastin_ai.rag.indexing.
- Duties: Defines DocumentIndexer and related helper logic.
- Depends on: Project modules: rastin_ai.rag.chunking.base,
  rastin_ai.rag.embeddings.base, rastin_ai.rag.exceptions,
  rastin_ai.rag.loaders.base, rastin_ai.rag.models, and 1 more.
"""

import hashlib
import logging
from pathlib import Path

from rastin_ai.observability import observed_span, safe_update_observation
from rastin_ai.rag.chunking.base import TextChunker
from rastin_ai.rag.embeddings.base import EmbeddingProvider
from rastin_ai.rag.exceptions import EmbeddingError, VectorStoreError
from rastin_ai.rag.loaders.base import DocumentLoader
from rastin_ai.rag.models import Chunk, IndexingSummary
from rastin_ai.rag.vectorstores.base import VectorStore

logger = logging.getLogger(__name__)


class DocumentIndexer:
    """Coordinate deterministic document load, chunk, embed, and index steps."""

    def __init__(
        self,
        *,
        loader: DocumentLoader,
        chunker: TextChunker,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self._loader = loader
        self._chunker = chunker
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    def index(
        self,
        path: str | Path,
        *,
        document_id: str | None = None,
        user_id: str | None = None,
        replace_existing: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> IndexingSummary:
        metadata = metadata or {}
        with observed_span(
            name="document.extraction.load",
            input={
                "document_id": document_id,
                "extension": Path(path).suffix.lower() or None,
            },
            metadata={"document_id": document_id},
        ) as observation:
            documents = self._loader.load(path)
            safe_update_observation(
                observation,
                output={"document_count": len(documents)},
            )

        with observed_span(
            name="document.chunk",
            input={
                "document_id": document_id,
                "document_count": len(documents),
            },
            metadata={"document_id": document_id},
        ) as observation:
            chunks = self._chunker.split(documents)
            safe_update_observation(
                observation,
                output={"chunk_count": len(chunks)},
            )
        if document_id is not None:
            chunks = self._chunks_for_logical_document(
                chunks,
                document_id=document_id,
                user_id=user_id,
                metadata=metadata,
            )

        if not chunks:
            msg = "Indexing produced no chunks."
            raise VectorStoreError(msg)

        with observed_span(
            name="document.embedding",
            input={
                "document_id": document_id,
                "chunk_count": len(chunks),
            },
            metadata={"document_id": document_id},
        ) as observation:
            embeddings = self._embedding_provider.embed_documents(
                [chunk.text for chunk in chunks],
            )
            safe_update_observation(
                observation,
                output={"embedding_count": len(embeddings)},
            )
        if len(embeddings) != len(chunks):
            msg = (
                "Embedding provider returned a different number of embeddings "
                "than chunks."
            )
            raise EmbeddingError(msg)

        if replace_existing and document_id is not None:
            with observed_span(
                name="qdrant.delete_document_chunks",
                input={"document_id": document_id, "user_id": user_id},
                metadata={"document_id": document_id, "user_id": user_id},
            ) as observation:
                self._vector_store.delete(document_id=document_id, user_id=user_id)
                safe_update_observation(observation, output={"status": "deleted"})
        with observed_span(
            name="qdrant.upsert_document_chunks",
            input={"document_id": document_id, "chunk_count": len(chunks)},
            metadata={"document_id": document_id},
        ) as observation:
            self._vector_store.upsert(chunks, embeddings)
            safe_update_observation(
                observation,
                output={"status": "upserted", "chunk_count": len(chunks)},
            )

        summary = IndexingSummary(
            document_count=len(documents),
            chunk_count=len(chunks),
            document_ids=(
                (document_id,)
                if document_id is not None
                else tuple(document.id for document in documents)
            ),
            chunk_ids=tuple(chunk.id for chunk in chunks),
        )
        logger.info(
            "Document indexing completed",
            extra={
                "document_count": summary.document_count,
                "chunk_count": summary.chunk_count,
            },
        )
        return summary

    @staticmethod
    def _chunks_for_logical_document(
        chunks: list[Chunk],
        *,
        document_id: str,
        user_id: str | None,
        metadata: dict[str, object],
    ) -> list[Chunk]:
        logical_chunks = []
        for logical_index, chunk in enumerate(chunks):
            chunk_metadata = {
                **chunk.metadata,
                **metadata,
                "document_id": document_id,
                "user_id": user_id,
                "loader_document_id": chunk.document_id,
                "source_chunk_index": chunk.chunk_index,
            }
            logical_chunks.append(
                Chunk(
                    id=_logical_chunk_id(document_id, logical_index, chunk.text),
                    document_id=document_id,
                    text=chunk.text,
                    chunk_index=logical_index,
                    metadata=chunk_metadata,
                    token_count=chunk.token_count,
                )
            )
        return logical_chunks


def _logical_chunk_id(document_id: str, chunk_index: int, text: str) -> str:
    digest = hashlib.sha256(f"{document_id}:{chunk_index}:{text}".encode()).hexdigest()
    return f"chunk_{digest[:24]}"
