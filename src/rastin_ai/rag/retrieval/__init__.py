"""File guide.

- Use: Exports retrieval helpers.
- Usage: Import from rastin_ai.rag.retrieval.__init__ to use the package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules: rastin_ai.rag.retrieval.retriever.
"""

from rastin_ai.rag.retrieval.retriever import Retriever

__all__ = ["Retriever"]
