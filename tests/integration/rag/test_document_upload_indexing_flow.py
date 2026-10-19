"""File guide.

- Use: Integration test for upload persistence followed by real Qdrant indexing.
- Usage: Run with pytest when Postgres and Qdrant test services are available.
- Duties: Exercises storage, PostgreSQL document metadata, and Qdrant payloads.
- Depends on: Project modules: database, rag, repositories, services, and storage.
"""

import asyncio
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from rastin_ai.database import Base
from rastin_ai.database.engine import create_database_engine
from rastin_ai.database.enums import DocumentStatus
from rastin_ai.database.models.user import User
from rastin_ai.database.session import create_session_factory
from rastin_ai.rag.chunking.recursive import RecursiveTextChunker
from rastin_ai.rag.indexing import DocumentIndexer
from rastin_ai.rag.retrieval.retriever import Retriever
from rastin_ai.rag.vectorstores.qdrant import QdrantVectorStore
from rastin_ai.repositories.documents import SQLAlchemyDocumentRepository
from rastin_ai.services.document_ingestion import SynchronousDocumentIngestionService
from rastin_ai.services.documents import DocumentUpload, StoredDocumentService
from rastin_ai.services.upload import UploadService
from rastin_ai.storage.local import LocalStorageProvider

TEST_DATABASE_URL = os.environ.get("RASTIN_AI_TEST_DATABASE_URL")
TEST_QDRANT_URL = os.environ.get("RASTIN_AI_TEST_QDRANT_URL")
USER_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


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


def test_document_upload_persists_and_indexes_into_real_qdrant(tmp_path: Path) -> None:
    if not TEST_DATABASE_URL:
        pytest.skip("RASTIN_AI_TEST_DATABASE_URL is required for this test.")
    if not _is_safe_test_database_url(TEST_DATABASE_URL):
        pytest.skip(
            "RASTIN_AI_TEST_DATABASE_URL must point to a database ending in _test.",
        )
    if not TEST_QDRANT_URL:
        pytest.skip("RASTIN_AI_TEST_QDRANT_URL is required for this test.")

    asyncio.run(_run_document_upload_indexing_flow(tmp_path))


def _is_safe_test_database_url(database_url: str | None) -> bool:
    if not database_url:
        return False

    try:
        database_name = make_url(database_url).database
    except ArgumentError:
        return False

    return bool(database_name and database_name.endswith("_test"))


async def _run_document_upload_indexing_flow(tmp_path: Path) -> None:
    engine = create_database_engine(TEST_DATABASE_URL)
    collection_name = f"test_upload_indexing_{uuid.uuid4().hex}"
    vector_store = QdrantVectorStore(
        collection_name=collection_name,
        dimension=KeywordEmbeddingProvider.dimension,
        url=TEST_QDRANT_URL,
        wait=True,
    )

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            session.add(
                User(
                    id=USER_ID,
                    issuer="test",
                    external_subject="document-upload-indexing",
                    email="document-upload-indexing@example.test",
                )
            )
            await session.commit()
            repository = SQLAlchemyDocumentRepository(session)
            storage = LocalStorageProvider(tmp_path)
            embedder = KeywordEmbeddingProvider()
            ingestion = SynchronousDocumentIngestionService(
                storage_provider=storage,
                document_repository=repository,
                indexer_factory=lambda loader: DocumentIndexer(
                    loader=loader,
                    chunker=RecursiveTextChunker(chunk_size=24, chunk_overlap=0),
                    embedding_provider=embedder,
                    vector_store=vector_store,
                ),
            )
            document_service = StoredDocumentService(
                upload_service=UploadService(
                    storage,
                    repository,
                    user_id=USER_ID,
                ),
                document_repository=repository,
                ingestion_service=ingestion,
                user_id=USER_ID,
            )

            record = await document_service.upload_document(
                DocumentUpload(
                    filename="knowledge.csv",
                    content=(
                        b"topic,value\n"
                        b"alpha,alpha operational context\n"
                        b"beta,beta secondary context\n"
                        b"gamma,gamma tertiary context\n"
                    ),
                    content_type="text/csv",
                )
            )
            persisted = await repository.get_by_id(record.document_id, user_id=USER_ID)

        assert persisted is not None
        assert persisted.status == DocumentStatus.INDEXED.value
        assert persisted.indexing_error_code is None
        assert persisted.file_metadata_id == record.file_metadata_id

        results = Retriever(
            embedding_provider=KeywordEmbeddingProvider(),
            vector_store=vector_store,
        ).retrieve(
            "alpha",
            top_k=3,
            filters={
                "document_id": str(record.document_id),
                "user_id": str(USER_ID),
            },
        )

        assert results
        assert all(
            result.chunk.document_id == str(record.document_id) for result in results
        )
        assert all(result.chunk.metadata["file_type"] == "csv" for result in results)
        assert all(
            result.chunk.metadata["source_location"].startswith("rows:")
            for result in results
        )
    finally:
        vector_store.delete_collection()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()
