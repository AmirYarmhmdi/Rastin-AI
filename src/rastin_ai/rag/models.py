"""File guide.

- Use: Defines shared Pydantic models for documents, chunks, retrieval, and
  indexing.
- Usage: Import BuiltContext, Chunk, Document, and 2 more from
  rastin_ai.rag.models.
- Duties: Defines BuiltContext, Chunk, Document, IndexingSummary, and RetrievedChunk
  and related helper logic.
- Depends on: External packages only: pydantic, and typing.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

Metadata = dict[str, Any]


class Document(BaseModel):
    """Normalized source document used by the RAG pipeline."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    text: str
    source: str = Field(min_length=1)
    metadata: Metadata = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def validate_text(cls, text: str) -> str:
        if not text.strip():
            msg = "Document text must not be empty."
            raise ValueError(msg)
        return text


class Chunk(BaseModel):
    """A deterministic text segment derived from a parent document."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    text: str
    chunk_index: int = Field(ge=0)
    metadata: Metadata = Field(default_factory=dict)
    token_count: int = Field(ge=0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, text: str) -> str:
        if not text.strip():
            msg = "Chunk text must not be empty."
            raise ValueError(msg)
        return text


class RetrievedChunk(BaseModel):
    """A chunk returned by vector retrieval with its similarity score."""

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    score: float


class IndexingSummary(BaseModel):
    """Summary returned after a document indexing run."""

    model_config = ConfigDict(frozen=True)

    document_count: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    document_ids: tuple[str, ...] = ()
    chunk_ids: tuple[str, ...] = ()


class BuiltContext(BaseModel):
    """LLM-ready deterministic context and structured source records."""

    model_config = ConfigDict(frozen=True)

    text: str
    sources: tuple[dict[str, Any], ...] = ()
