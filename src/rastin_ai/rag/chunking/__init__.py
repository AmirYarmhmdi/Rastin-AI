"""File guide.

- Use: Exports text chunking contracts and implementations.
- Usage: Import from rastin_ai.rag.chunking.__init__ to use the package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules: rastin_ai.rag.chunking.base, and
  rastin_ai.rag.chunking.recursive.
"""

from rastin_ai.rag.chunking.base import TextChunker
from rastin_ai.rag.chunking.recursive import (
    RecursiveChunkerConfig,
    RecursiveTextChunker,
)

__all__ = ["RecursiveChunkerConfig", "RecursiveTextChunker", "TextChunker"]
