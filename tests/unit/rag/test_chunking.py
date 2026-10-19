"""File guide.

- Use: Contains unit tests for chunking behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.rag.chunking.recursive, and
  rastin_ai.rag.models.
"""

import pytest
from pydantic import ValidationError

from rastin_ai.rag.chunking.recursive import (
    RecursiveChunkerConfig,
    RecursiveTextChunker,
)
from rastin_ai.rag.models import Document


def test_recursive_chunker_is_deterministic_and_overlaps() -> None:
    document = Document(
        id="doc-1",
        text="one two three four five six seven",
        source="notes.txt",
        metadata={"filename": "notes.txt"},
    )
    chunker = RecursiveTextChunker(chunk_size=3, chunk_overlap=1)

    first = chunker.split([document])
    second = chunker.split([document])

    assert [chunk.text for chunk in first] == [
        "one two three",
        "three four five",
        "five six seven",
    ]
    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert [chunk.chunk_index for chunk in first] == [0, 1, 2]


def test_recursive_chunker_inherits_metadata_and_avoids_empty_chunks() -> None:
    document = Document(
        id="doc-1",
        text="  alpha   beta  ",
        source="notes.txt",
        metadata={"project_id": "project-1"},
    )

    chunks = RecursiveTextChunker(chunk_size=10, chunk_overlap=0).split([document])

    assert len(chunks) == 1
    assert chunks[0].metadata["project_id"] == "project-1"
    assert chunks[0].metadata["document_id"] == "doc-1"
    assert chunks[0].metadata["chunk_index"] == 0
    assert chunks[0].token_count == 2


def test_recursive_chunker_rejects_invalid_configuration() -> None:
    with pytest.raises(ValidationError, match="chunk_overlap"):
        RecursiveChunkerConfig(chunk_size=3, chunk_overlap=3)
