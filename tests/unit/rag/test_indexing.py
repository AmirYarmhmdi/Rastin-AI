"""File guide.

- Use: Contains unit tests for indexing behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.rag.indexing, and
  rastin_ai.rag.models.
"""

from pathlib import Path

from rastin_ai.rag.indexing import DocumentIndexer
from rastin_ai.rag.models import Chunk, Document


class FakeLoader:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def load(self, path: str | Path) -> list[Document]:
        self.paths.append(Path(path))
        return [
            Document(
                id="doc-1",
                text="alpha beta gamma",
                source="notes.txt",
                metadata={"filename": "notes.txt"},
            )
        ]


class FakeChunker:
    def __init__(self) -> None:
        self.documents: list[Document] = []

    def split(self, documents: list[Document]) -> list[Chunk]:
        self.documents.extend(documents)
        return [
            Chunk(
                id="chunk-1",
                document_id=documents[0].id,
                text="alpha beta",
                chunk_index=0,
                metadata={"filename": "notes.txt"},
                token_count=2,
            )
        ]


class FakeEmbeddingProvider:
    dimension = 2

    def __init__(self) -> None:
        self.texts: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.texts.extend(texts)
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


class FakeVectorStore:
    def __init__(self) -> None:
        self.upserts: list[tuple[list[Chunk], list[list[float]]]] = []
        self.deleted_document_ids: list[str] = []

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        self.upserts.append((chunks, embeddings))

    def search(self, *args, **kwargs):
        return []

    def delete(self, *args, **kwargs) -> None:
        self.deleted_document_ids.append(kwargs["document_id"])


def test_document_indexer_orchestrates_load_chunk_embed_and_upsert(
    tmp_path: Path,
) -> None:
    loader = FakeLoader()
    chunker = FakeChunker()
    embedder = FakeEmbeddingProvider()
    vector_store = FakeVectorStore()
    indexer = DocumentIndexer(
        loader=loader,
        chunker=chunker,
        embedding_provider=embedder,
        vector_store=vector_store,
    )
    path = tmp_path / "notes.txt"

    summary = indexer.index(path)

    assert loader.paths == [path]
    assert chunker.documents[0].id == "doc-1"
    assert embedder.texts == ["alpha beta"]
    assert vector_store.upserts[0][1] == [[1.0, 0.0]]
    assert summary.document_count == 1
    assert summary.chunk_count == 1
    assert summary.document_ids == ("doc-1",)
    assert summary.chunk_ids == ("chunk-1",)


def test_document_indexer_can_replace_chunks_for_logical_document_id(
    tmp_path: Path,
) -> None:
    loader = FakeLoader()
    chunker = FakeChunker()
    embedder = FakeEmbeddingProvider()
    vector_store = FakeVectorStore()
    indexer = DocumentIndexer(
        loader=loader,
        chunker=chunker,
        embedding_provider=embedder,
        vector_store=vector_store,
    )
    logical_document_id = "11111111-1111-4111-8111-111111111111"

    summary = indexer.index(
        tmp_path / "notes.txt",
        document_id=logical_document_id,
        replace_existing=True,
        metadata={"file_metadata_id": "file-1"},
    )

    chunks, _ = vector_store.upserts[0]
    assert vector_store.deleted_document_ids == [logical_document_id]
    assert chunks[0].document_id == logical_document_id
    assert chunks[0].metadata["document_id"] == logical_document_id
    assert chunks[0].metadata["loader_document_id"] == "doc-1"
    assert chunks[0].metadata["file_metadata_id"] == "file-1"
    assert summary.document_ids == (logical_document_id,)
