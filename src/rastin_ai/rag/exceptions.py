"""File guide.

- Use: Defines errors raised by the RAG pipeline.
- Usage: Import ChunkingError, ContextBuildError, DocumentLoadError, and 5 more from
  rastin_ai.rag.exceptions.
- Duties: Defines ChunkingError, ContextBuildError, DocumentLoadError,
  EmbeddingError, EmptyDocumentError, and 3 more and related helper logic.
- Depends on: No direct project module dependencies.
"""


class RAGError(Exception):
    """Base error for deterministic RAG pipeline failures."""


class DocumentLoadError(RAGError):
    """Raised when a document cannot be loaded or normalized."""


class EmptyDocumentError(DocumentLoadError):
    """Raised when a loader receives a document without usable text."""


class ChunkingError(RAGError):
    """Raised when text chunking cannot be completed."""


class EmbeddingError(RAGError):
    """Raised when embedding generation fails or returns invalid output."""


class VectorStoreError(RAGError):
    """Raised when vector storage or retrieval fails."""


class RetrieverError(RAGError):
    """Raised when retrieval cannot be completed."""


class ContextBuildError(RAGError):
    """Raised when retrieved context cannot be formatted."""
