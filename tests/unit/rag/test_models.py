"""File guide.

- Use: Contains unit tests for models behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.rag.models.
"""

import pytest
from pydantic import ValidationError

from rastin_ai.rag.models import Chunk, Document, RetrievedChunk


def test_document_preserves_extensible_metadata() -> None:
    document = Document(
        id="doc-1",
        text="Hello world",
        source="/tmp/notes.txt",
        metadata={"project_id": "project-1", "tags": ["alpha"]},
    )

    assert document.metadata["project_id"] == "project-1"
    assert document.metadata["tags"] == ["alpha"]


def test_document_rejects_empty_text() -> None:
    with pytest.raises(ValidationError):
        Document(id="doc-1", text="  ", source="/tmp/empty.txt")


def test_chunk_validation_and_retrieved_chunk_score() -> None:
    chunk = Chunk(
        id="chunk-1",
        document_id="doc-1",
        text="useful content",
        chunk_index=0,
        metadata={"source": "notes.txt", "page_number": 3},
        token_count=2,
    )

    retrieved = RetrievedChunk(chunk=chunk, score=0.91)

    assert retrieved.chunk.metadata["page_number"] == 3
    assert retrieved.score == 0.91


def test_chunk_rejects_negative_index() -> None:
    with pytest.raises(ValidationError):
        Chunk(
            id="chunk-1",
            document_id="doc-1",
            text="content",
            chunk_index=-1,
            token_count=1,
        )
