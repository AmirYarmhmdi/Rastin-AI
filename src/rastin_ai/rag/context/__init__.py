"""File guide.

- Use: Exports context-building helpers for retrieval results.
- Usage: Import from rastin_ai.rag.context.__init__ to use the package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules: rastin_ai.rag.context.builder.
"""

from rastin_ai.rag.context.builder import ContextBuilder, ContextBuilderConfig

__all__ = ["ContextBuilder", "ContextBuilderConfig"]
