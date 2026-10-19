"""File guide.

- Use: Exports embedding provider contracts and implementations.
- Usage: Import from rastin_ai.rag.embeddings.__init__ to use the package API.
- Duties: Keeps package imports short and stable for other modules.
- Depends on: Project modules: rastin_ai.rag.embeddings.base, and
  rastin_ai.rag.embeddings.openai.
"""

from rastin_ai.rag.embeddings.base import EmbeddingProvider
from rastin_ai.rag.embeddings.openai import (
    OpenAIEmbeddingConfig,
    OpenAIEmbeddingProvider,
)

__all__ = ["EmbeddingProvider", "OpenAIEmbeddingConfig", "OpenAIEmbeddingProvider"]
