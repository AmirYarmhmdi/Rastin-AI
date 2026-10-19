"""File guide.

- Use: Contains integration tests for qdrant rag pipeline behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.rag.chunking.recursive,
  rastin_ai.rag.context.builder, rastin_ai.rag.indexing,
  rastin_ai.rag.loaders.text, rastin_ai.rag.retrieval.retriever, and 1 more.
"""

import os
import uuid
from pathlib import Path

import pytest

from rastin_ai.rag.chunking.recursive import RecursiveTextChunker
from rastin_ai.rag.context.builder import ContextBuilder
from rastin_ai.rag.indexing import DocumentIndexer
from rastin_ai.rag.loaders.text import TextFileLoader
from rastin_ai.rag.retrieval.retriever import Retriever
from rastin_ai.rag.vectorstores.qdrant import QdrantVectorStore

TEST_QDRANT_URL = os.environ.get("RASTIN_AI_TEST_QDRANT_URL")


class KeywordEmbeddingProvider:
    dimension = 3

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        normalized = text.lower()
        return [
            float(normalized.count("alpha")),
            float(normalized.count("beta")),
            float(normalized.count("gamma")),
        ]


@pytest.mark.skipif(
    not TEST_QDRANT_URL,
    reason="RASTIN_AI_TEST_QDRANT_URL is required for Qdrant integration tests.",
)
def test_document_to_qdrant_to_retrieval_context(tmp_path: Path) -> None:
    from qdrant_client import QdrantClient

    collection_name = f"test_rag_{uuid.uuid4().hex}"
    client = QdrantClient(url=TEST_QDRANT_URL)
    vector_store = QdrantVectorStore(
        collection_name=collection_name,
        dimension=KeywordEmbeddingProvider.dimension,
        client=client,
    )

    try:
        path = tmp_path / "knowledge.txt"
        path.write_text(
            "alpha alpha operational context\n"
            "beta secondary context\n"
            "gamma tertiary context\n",
            encoding="utf-8",
        )
        embedder = KeywordEmbeddingProvider()
        indexer = DocumentIndexer(
            loader=TextFileLoader(),
            chunker=RecursiveTextChunker(chunk_size=4, chunk_overlap=0),
            embedding_provider=embedder,
            vector_store=vector_store,
        )

        summary = indexer.index(path)
        results = Retriever(
            embedding_provider=embedder,
            vector_store=vector_store,
        ).retrieve("alpha", top_k=1)
        context = ContextBuilder().build(results)

        assert summary.document_count == 1
        assert summary.chunk_count == 3
        assert results[0].chunk.text == "alpha alpha operational context"
        assert "File: knowledge.txt" in context.text
        assert "alpha alpha operational context" in context.text
    finally:
        client.delete_collection(collection_name=collection_name)
