"""File guide.

- Use: Exports document loader contracts and implementations.
- Usage: Import from rastin_ai.rag.loaders.__init__ to use the package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules: rastin_ai.rag.extraction,
  rastin_ai.rag.loaders.base, rastin_ai.rag.loaders.pdf, and
  rastin_ai.rag.loaders.text.
"""

from rastin_ai.rag.extraction import (
    DefaultDocumentExtractor,
    DocumentExtractionError,
    ExtractionResult,
    SharedDocumentLoader,
)
from rastin_ai.rag.loaders.base import DocumentLoader
from rastin_ai.rag.loaders.pdf import PDFLoader
from rastin_ai.rag.loaders.text import TextFileLoader

__all__ = [
    "DefaultDocumentExtractor",
    "DocumentExtractionError",
    "DocumentLoader",
    "ExtractionResult",
    "PDFLoader",
    "SharedDocumentLoader",
    "TextFileLoader",
]
