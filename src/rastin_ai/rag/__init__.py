"""File guide.

- Use: Exports the main RAG pipeline classes and models.
- Usage: Import from rastin_ai.rag.__init__ to use the package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules: rastin_ai.rag.chunking.recursive,
  rastin_ai.rag.context.builder, rastin_ai.rag.indexing,
  rastin_ai.rag.loaders.pdf, rastin_ai.rag.loaders.text, and 2 more.
"""

from rastin_ai.rag.chunking.recursive import (
    RecursiveChunkerConfig,
    RecursiveTextChunker,
)
from rastin_ai.rag.context.builder import ContextBuilder, ContextBuilderConfig
from rastin_ai.rag.indexing import DocumentIndexer
from rastin_ai.rag.loaders.pdf import PDFLoader
from rastin_ai.rag.loaders.text import TextFileLoader
from rastin_ai.rag.models import BuiltContext, Chunk, Document, RetrievedChunk
from rastin_ai.rag.retrieval.retriever import Retriever

__all__ = [
    "BuiltContext",
    "Chunk",
    "ContextBuilder",
    "ContextBuilderConfig",
    "Document",
    "DocumentIndexer",
    "PDFLoader",
    "RecursiveChunkerConfig",
    "RecursiveTextChunker",
    "RetrievedChunk",
    "Retriever",
    "TextFileLoader",
]
