"""File guide.

- Use: Defines the document loader contract for the RAG pipeline.
- Usage: Import DocumentLoader from rastin_ai.rag.loaders.base.
- Duties: Defines DocumentLoader and related helper logic.
- Depends on: Project modules: rastin_ai.rag.models.
"""

from pathlib import Path
from typing import Protocol

from rastin_ai.rag.models import Document


class DocumentLoader(Protocol):
    """Load and normalize source files into RAG documents."""

    def load(self, path: str | Path) -> list[Document]:
        """Load one logical input into one or more normalized documents."""
