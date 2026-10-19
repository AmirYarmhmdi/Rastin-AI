"""File guide.

- Use: End-to-end tests for Rastin-AI's real API/runtime infrastructure.
- Usage: Run with RASTIN_AI_E2E=1 and disposable Postgres/Qdrant services.
- Duties: Proves upload, indexing, RAG, conversations, routing, and failure
  isolation across public API, PostgreSQL, local storage, and Qdrant.
- Depends on: External services PostgreSQL/Qdrant. Project modules: API,
  database, RAG, services, and storage.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest
from alembic.config import Config
from fastapi import Depends
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient
from qdrant_client import models as qdrant_models
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from alembic import command
from rastin_ai.database.engine import create_database_engine, get_engine
from rastin_ai.database.enums import (
    DocumentScope,
    DocumentStatus,
    WorkflowExecutionStatus,
)
from rastin_ai.database.models.conversation_message import ConversationMessage
from rastin_ai.database.models.conversation_message_document import (
    ConversationMessageDocument,
)
from rastin_ai.database.models.document import Document as DocumentModel
from rastin_ai.database.models.file_metadata import FileMetadata
from rastin_ai.database.models.user import User
from rastin_ai.database.models.workflow_execution import WorkflowExecution
from rastin_ai.database.session import create_session_factory, get_session_factory
from rastin_ai.rag.chunking.recursive import RecursiveTextChunker
from rastin_ai.rag.context.builder import ContextBuilder
from rastin_ai.rag.indexing import DocumentIndexer
from rastin_ai.rag.retrieval.retriever import Retriever
from rastin_ai.rag.vectorstores.qdrant import QdrantVectorStore
from rastin_ai.security.auth import AuthenticatedPrincipal
from rastin_ai.services.document_ingestion import (
    DocumentIngestionService,
    SynchronousDocumentIngestionService,
)
from rastin_ai.services.documents import DocumentService
from rastin_ai.services.project_documents import (
    ProjectDocumentService,
    StoredProjectDocumentService,
)
from rastin_ai.services.questions import (
    QuestionAnsweringService,
    RAGQuestionAnsweringService,
)
from rastin_ai.storage.local import LocalStorageProvider

pytestmark = pytest.mark.e2e

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("RASTIN_AI_TEST_DATABASE_URL")
TEST_QDRANT_URL = os.environ.get("RASTIN_AI_TEST_QDRANT_URL")
E2E_ENABLED = os.environ.get("RASTIN_AI_E2E") == "1"
AUTH_ISSUER = "https://issuer.e2e.rastin_ai.test"
AUTH_AUDIENCE = "rastin-ai-e2e"
AUTH_SECRET = "rastin-ai-e2e-dev-secret-at-least-32-bytes"


class KeywordEmbeddingProvider:
    dimension = 4

    def __init__(self) -> None:
        self.document_calls = 0
        self.query_calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls += 1
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        normalized = text.lower()
        return [
            float(normalized.count("alpha")),
            float(normalized.count("beta")),
            float(normalized.count("gamma")),
            float(normalized.count("comparison") + normalized.count("compare")),
        ]


class DeterministicResponseGenerator:
    def __init__(self, recorder: E2ERecorder) -> None:
        self._recorder = recorder

    def generate_response(self, **kwargs: Any) -> str:
        self._recorder.response_calls.append(dict(kwargs))
        tool_result = kwargs.get("tool_result")
        citations = []
        if isinstance(tool_result, dict):
            citations = list(tool_result.get("citations") or ())
        return f"Deterministic answer from {len(citations)} cited source(s)."


class DeterministicAgentGraph:
    def __init__(self, recorder: E2ERecorder) -> None:
        self._recorder = recorder

    def invoke(
        self,
        input: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._recorder.graph_calls.append({"input": input, "config": config})
        metadata = (config or {}).get("metadata") or {}
        return {
            "response": "Deterministic LangGraph comparison.",
            "plan": ["compare selected logical documents"],
            "citations": (
                {
                    "document_id": self._recorder.primary_document_id,
                    "chunk_id": "deterministic-langgraph-citation",
                    "source_location": "graph:deterministic",
                },
            ),
            "sources": (
                {
                    "document_id": self._recorder.primary_document_id,
                    "chunk_id": "deterministic-langgraph-citation",
                    "source_location": "graph:deterministic",
                },
            ),
            "metadata": metadata,
        }


@dataclass
class E2ERecorder:
    embedder: KeywordEmbeddingProvider = field(default_factory=KeywordEmbeddingProvider)
    response_calls: list[dict[str, Any]] = field(default_factory=list)
    graph_calls: list[dict[str, Any]] = field(default_factory=list)
    primary_document_id: str | None = None


@dataclass
class E2ERuntime:
    client: TestClient
    storage: LocalStorageProvider
    storage_root: Path
    database_url: str
    qdrant_url: str
    collection_name: str
    recorder: E2ERecorder

    def headers(self, subject: str = "user-a") -> dict[str, str]:
        return {"Authorization": f"Bearer {_dev_token(subject)}"}

    async def scalar(self, statement: Any) -> Any:
        engine = create_database_engine(self.database_url)
        try:
            session_factory = create_session_factory(engine)
            async with session_factory() as session:
                return await session.scalar(statement)
        finally:
            await engine.dispose()

    async def scalars(self, statement: Any) -> list[Any]:
        engine = create_database_engine(self.database_url)
        try:
            session_factory = create_session_factory(engine)
            async with session_factory() as session:
                result = await session.scalars(statement)
                return list(result.all())
        finally:
            await engine.dispose()


@pytest.fixture()
def e2e_runtime(monkeypatch, tmp_path: Path) -> Iterator[E2ERuntime]:
    _require_e2e_environment()
    assert TEST_DATABASE_URL is not None
    assert TEST_QDRANT_URL is not None

    collection_name = f"rastin_ai_e2e_{uuid.uuid4().hex}"
    storage_root = tmp_path / "storage"
    recorder = E2ERecorder()

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("QDRANT_URL", TEST_QDRANT_URL)
    monkeypatch.setenv("QDRANT_COLLECTION_NAME", collection_name)
    monkeypatch.setenv("OPENAI_API_KEY", "not-used-by-e2e-doubles")
    monkeypatch.setenv("OPENAI_PLANNER_MODEL", "deterministic-planner")
    monkeypatch.setenv("OPENAI_RESPONSE_MODEL", "deterministic-response")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "deterministic-embedding")
    monkeypatch.setenv(
        "RAG_EMBEDDING_DIMENSION", str(KeywordEmbeddingProvider.dimension)
    )
    monkeypatch.setenv("RAG_CHUNK_SIZE", "40")
    monkeypatch.setenv("RAG_CHUNK_OVERLAP", "0")
    monkeypatch.setenv("RAG_RETRIEVAL_TOP_K", "5")
    monkeypatch.setenv("RAG_CONTEXT_MAX_CHARS", "6000")
    monkeypatch.setenv("CONVERSATION_HISTORY_MAX_TURNS", "4")
    monkeypatch.setenv("CONVERSATION_HISTORY_MAX_CHARS", "2000")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("AUTH_MODE", "dev_jwt")
    monkeypatch.setenv("AUTH_DEV_JWT_ISSUER", AUTH_ISSUER)
    monkeypatch.setenv("AUTH_DEV_JWT_AUDIENCE", AUTH_AUDIENCE)
    monkeypatch.setenv("AUTH_DEV_JWT_SECRET", AUTH_SECRET)

    _reset_database(TEST_DATABASE_URL)
    _run_migrations()
    _delete_qdrant_collection(TEST_QDRANT_URL, collection_name)
    _reset_app_modules()

    main = importlib.import_module("rastin_ai.main")
    dependencies = importlib.import_module("rastin_ai.api.dependencies")
    app = main.create_app()
    storage = LocalStorageProvider(storage_root)
    settings_dependency = Depends(dependencies.get_settings)
    storage_provider_dependency = Depends(dependencies.get_storage_provider)
    document_repository_dependency = Depends(dependencies.get_document_repository)
    document_service_dependency = Depends(dependencies.get_document_service)
    workflow_repository_dependency = Depends(
        dependencies.get_workflow_execution_repository
    )
    project_document_repository_dependency = Depends(
        dependencies.get_project_document_repository
    )
    authorization_service_dependency = Depends(dependencies.get_authorization_service)
    principal_dependency = Depends(dependencies.get_current_principal)

    def override_storage_provider() -> LocalStorageProvider:
        return storage

    def override_ingestion_service(
        settings=settings_dependency,
        storage_provider=storage_provider_dependency,
        document_repository=document_repository_dependency,
    ) -> DocumentIngestionService:
        return SynchronousDocumentIngestionService(
            storage_provider=storage_provider,
            document_repository=document_repository,
            indexer_factory=lambda loader: DocumentIndexer(
                loader=loader,
                chunker=RecursiveTextChunker(
                    chunk_size=settings.RAG_CHUNK_SIZE,
                    chunk_overlap=settings.RAG_CHUNK_OVERLAP,
                ),
                embedding_provider=recorder.embedder,
                vector_store=_vector_store(settings.QDRANT_COLLECTION_NAME),
            ),
        )

    def override_question_service(
        settings=settings_dependency,
        document_service: DocumentService = document_service_dependency,
        workflow_repository=workflow_repository_dependency,
        principal: AuthenticatedPrincipal = principal_dependency,
    ) -> QuestionAnsweringService:
        return RAGQuestionAnsweringService(
            retriever=Retriever(
                embedding_provider=recorder.embedder,
                vector_store=_vector_store(settings.QDRANT_COLLECTION_NAME),
            ),
            context_builder=ContextBuilder(max_chars=settings.RAG_CONTEXT_MAX_CHARS),
            response_generator=DeterministicResponseGenerator(recorder),
            document_service=document_service,
            workflow_repository=workflow_repository,
            user_id=principal.user_id,
            top_k=settings.RAG_RETRIEVAL_TOP_K,
        )

    def override_project_document_service(
        settings=settings_dependency,
        storage_provider=storage_provider_dependency,
        project_document_repository=project_document_repository_dependency,
        authorization_service=authorization_service_dependency,
    ) -> ProjectDocumentService:
        return StoredProjectDocumentService(
            storage_provider=storage_provider,
            project_document_repository=project_document_repository,
            authorization_service=authorization_service,
            vector_store_factory=lambda: _vector_store(settings.QDRANT_COLLECTION_NAME),
            indexer_factory=lambda loader: DocumentIndexer(
                loader=loader,
                chunker=RecursiveTextChunker(
                    chunk_size=settings.RAG_CHUNK_SIZE,
                    chunk_overlap=settings.RAG_CHUNK_OVERLAP,
                ),
                embedding_provider=recorder.embedder,
                vector_store=_vector_store(settings.QDRANT_COLLECTION_NAME),
            ),
            storage_backend=settings.STORAGE_BACKEND,
            max_upload_bytes=settings.MAX_UPLOAD_BYTES,
        )

    def override_agent_graph() -> DeterministicAgentGraph:
        return DeterministicAgentGraph(recorder)

    app.dependency_overrides[dependencies.get_storage_provider] = (
        override_storage_provider
    )
    app.dependency_overrides[dependencies.get_document_ingestion_service] = (
        override_ingestion_service
    )
    app.dependency_overrides[dependencies.get_question_answering_service] = (
        override_question_service
    )
    app.dependency_overrides[dependencies.get_project_document_service] = (
        override_project_document_service
    )
    app.dependency_overrides[dependencies.get_agent_graph] = override_agent_graph

    try:
        with TestClient(app) as client:
            yield E2ERuntime(
                client=client,
                storage=storage,
                storage_root=storage_root,
                database_url=TEST_DATABASE_URL,
                qdrant_url=TEST_QDRANT_URL,
                collection_name=collection_name,
                recorder=recorder,
            )
    finally:
        _delete_qdrant_collection(TEST_QDRANT_URL, collection_name)
        _reset_database(TEST_DATABASE_URL)
        asyncio.run(_dispose_cached_engine())


def test_upload_index_and_persisted_document_qa(e2e_runtime: E2ERuntime) -> None:
    alpha = _upload(
        e2e_runtime,
        filename="alpha.md",
        content=b"# Alpha\nalpha policy cites gamma control.\n",
        content_type="text/markdown",
    )
    beta = _upload(
        e2e_runtime,
        filename="beta.md",
        content=b"# Beta\nbeta policy is unrelated.\n",
        content_type="text/markdown",
    )
    _assert_indexed(alpha)
    _assert_indexed(beta)
    e2e_runtime.recorder.primary_document_id = alpha["document_id"]

    assert alpha["file_metadata_id"] is not None
    assert alpha["checksum_sha256"]
    document = asyncio.run(
        e2e_runtime.scalar(
            select(DocumentModel).where(
                DocumentModel.id == uuid.UUID(alpha["document_id"])
            )
        )
    )
    file_metadata = asyncio.run(
        e2e_runtime.scalar(
            select(FileMetadata).where(
                FileMetadata.document_id == uuid.UUID(alpha["document_id"])
            )
        )
    )
    assert document is not None
    assert document.user_id is not None
    assert document.status == DocumentStatus.INDEXED.value
    assert file_metadata is not None
    assert str(file_metadata.document_id) == alpha["document_id"]
    assert file_metadata.user_id == document.user_id
    assert file_metadata.storage_backend == "local"
    assert e2e_runtime.storage.exists(file_metadata.storage_key) is True

    retrieved = _retrieve_qdrant(
        e2e_runtime,
        "alpha",
        alpha["document_id"],
        user_id=str(document.user_id),
    )
    assert retrieved
    assert all(result.chunk.document_id == alpha["document_id"] for result in retrieved)
    assert all(
        result.chunk.metadata["document_id"] == alpha["document_id"]
        for result in retrieved
    )

    response = e2e_runtime.client.post(
        "/api/v1/questions",
        json={"question": "alpha gamma", "document_ids": [alpha["document_id"]]},
        headers=e2e_runtime.headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "answered"
    assert payload["citations"]
    assert {citation["document_id"] for citation in payload["citations"]} == {
        alpha["document_id"]
    }
    assert "storage_key" not in str(payload["citations"])
    assert "files/" not in str(payload["citations"])

    cross_scope = e2e_runtime.client.post(
        "/api/v1/questions",
        json={"question": "beta", "document_ids": [alpha["document_id"]]},
        headers=e2e_runtime.headers(),
    )
    assert cross_scope.status_code == 200
    assert beta["document_id"] not in str(cross_scope.json())
    assert e2e_runtime.recorder.embedder.document_calls > 0


def test_persistent_multi_turn_conversation(e2e_runtime: E2ERuntime) -> None:
    document = _upload(
        e2e_runtime,
        filename="conversation.md",
        content=b"alpha roadmap evidence for the conversation.\n",
        content_type="text/markdown",
    )
    _assert_indexed(document)
    e2e_runtime.recorder.primary_document_id = document["document_id"]

    first = _submit_message(
        e2e_runtime,
        data=[
            ("message", "alpha roadmap"),
            ("document_ids", document["document_id"]),
        ],
    )
    assert first["status"] == "answered"
    assert first["session_id"]
    assert first["workflow_id"]
    assert first["citations"][0]["document_id"] == document["document_id"]

    second = _submit_message(
        e2e_runtime,
        data=[
            ("message", "alpha follow up"),
            ("session_id", first["session_id"]),
            ("document_ids", document["document_id"]),
        ],
    )
    assert second["session_id"] == first["session_id"]

    messages = asyncio.run(
        e2e_runtime.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == uuid.UUID(first["session_id"]))
            .order_by(ConversationMessage.sequence)
        )
    )
    assert [message.sequence for message in messages] == [1, 2, 3, 4]
    assert messages[0].workflow_id == uuid.UUID(first["workflow_id"])
    assert messages[1].workflow_id == uuid.UUID(first["workflow_id"])

    reference_count = asyncio.run(
        e2e_runtime.scalar(
            select(func.count()).select_from(ConversationMessageDocument)
        )
    )
    assert reference_count >= 2

    assert len(e2e_runtime.recorder.response_calls) >= 2
    follow_up_query = e2e_runtime.recorder.response_calls[-1]["user_query"]
    assert "Recent conversation:" in follow_up_query
    assert "alpha roadmap" in follow_up_query

    session_response = e2e_runtime.client.get(
        f"/api/v1/sessions/{first['session_id']}",
        headers=e2e_runtime.headers(),
    )
    assert session_response.status_code == 200
    session_payload = session_response.json()
    assert [message["sequence"] for message in session_payload["messages"]] == [
        1,
        2,
        3,
        4,
    ]
    assert (
        session_payload["messages"][0]["document_references"][0]["document_id"]
        == document["document_id"]
    )
    assert session_payload["messages"][1]["citations"]


def test_router_selects_direct_rag_and_langgraph(e2e_runtime: E2ERuntime) -> None:
    alpha = _upload(
        e2e_runtime,
        filename="router-alpha.md",
        content=b"alpha comparison evidence.\n",
        content_type="text/markdown",
    )
    beta = _upload(
        e2e_runtime,
        filename="router-beta.md",
        content=b"beta comparison evidence.\n",
        content_type="text/markdown",
    )
    _assert_indexed(alpha)
    _assert_indexed(beta)
    e2e_runtime.recorder.primary_document_id = alpha["document_id"]

    direct = _submit_message(
        e2e_runtime,
        data=[("message", "alpha"), ("document_ids", alpha["document_id"])],
    )
    direct_workflow = asyncio.run(
        e2e_runtime.scalar(
            select(WorkflowExecution).where(
                WorkflowExecution.id == uuid.UUID(direct["workflow_id"])
            )
        )
    )
    assert direct_workflow.input_payload["route"] == "direct_rag"
    assert direct_workflow.trace_id is None

    langgraph = _submit_message(
        e2e_runtime,
        data=[
            ("message", "Compare the selected documents and identify gaps."),
            ("document_ids", alpha["document_id"]),
            ("document_ids", beta["document_id"]),
        ],
    )
    assert langgraph["final_answer"] == "Deterministic LangGraph comparison."
    assert e2e_runtime.recorder.graph_calls
    langgraph_workflow = asyncio.run(
        e2e_runtime.scalar(
            select(WorkflowExecution).where(
                WorkflowExecution.id == uuid.UUID(langgraph["workflow_id"])
            )
        )
    )
    assert langgraph_workflow.workflow_name == "langgraph_orchestration"
    assert langgraph_workflow.input_payload["route"] == "langgraph"
    assert langgraph_workflow.status == WorkflowExecutionStatus.COMPLETED.value
    assert langgraph_workflow.trace_id is None


def test_failed_indexing_is_isolated_and_not_queryable(e2e_runtime: E2ERuntime) -> None:
    failed = _upload(
        e2e_runtime,
        filename="broken.json",
        content=b'{"alpha": ',
        content_type="application/json",
    )
    assert failed["status"] == DocumentStatus.FAILED.value
    assert failed["indexing_error_code"]
    failed_file_metadata = asyncio.run(
        e2e_runtime.scalar(
            select(FileMetadata).where(
                FileMetadata.document_id == uuid.UUID(failed["document_id"])
            )
        )
    )
    assert failed_file_metadata is not None
    assert e2e_runtime.storage.exists(failed_file_metadata.storage_key) is True

    failed_response = e2e_runtime.client.post(
        "/api/v1/questions",
        json={"question": "alpha", "document_ids": [failed["document_id"]]},
        headers=e2e_runtime.headers(),
    )
    assert failed_response.status_code == 200
    assert failed_response.json()["status"] == "indexing_failed"
    assert (
        _retrieve_qdrant(
            e2e_runtime,
            "alpha",
            failed["document_id"],
            user_id=str(failed_file_metadata.user_id),
        )
        == []
    )

    recovered = _upload(
        e2e_runtime,
        filename="recovered.md",
        content=b"alpha recovered evidence after failure.\n",
        content_type="text/markdown",
    )
    _assert_indexed(recovered)
    recovered_document = asyncio.run(
        e2e_runtime.scalar(
            select(DocumentModel).where(
                DocumentModel.id == uuid.UUID(recovered["document_id"])
            )
        )
    )
    assert recovered_document is not None
    assert _retrieve_qdrant(
        e2e_runtime,
        "alpha",
        recovered["document_id"],
        user_id=str(recovered_document.user_id),
    )


def test_two_users_are_isolated_through_public_api(e2e_runtime: E2ERuntime) -> None:
    user_a_document = _upload(
        e2e_runtime,
        filename="isolated-alpha.md",
        content=b"alpha private evidence.\n",
        content_type="text/markdown",
        subject="user-a",
    )
    user_b_document = _upload(
        e2e_runtime,
        filename="isolated-beta.md",
        content=b"beta private evidence.\n",
        content_type="text/markdown",
        subject="user-b",
    )
    _assert_indexed(user_a_document)
    _assert_indexed(user_b_document)
    e2e_runtime.recorder.primary_document_id = user_a_document["document_id"]

    assert "storage_key" not in user_a_document
    assert "storage_backend" not in user_a_document
    assert "storage_key" not in user_b_document
    assert "storage_backend" not in user_b_document

    user_a = _user_record(e2e_runtime, "user-a")
    user_b = _user_record(e2e_runtime, "user-b")
    user_a_file = _file_metadata(e2e_runtime, user_a_document["document_id"])
    user_b_file = _file_metadata(e2e_runtime, user_b_document["document_id"])
    assert user_a_file.user_id == user_a.id
    assert user_b_file.user_id == user_b.id
    assert user_a_file.storage_key.startswith(f"users/{user_a.id}/documents/")
    assert user_b_file.storage_key.startswith(f"users/{user_b.id}/documents/")
    assert e2e_runtime.storage.exists(user_a_file.storage_key) is True
    assert e2e_runtime.storage.exists(user_b_file.storage_key) is True

    user_a_listed = e2e_runtime.client.get(
        "/api/v1/documents",
        headers=e2e_runtime.headers("user-a"),
    )
    user_b_listed = e2e_runtime.client.get(
        "/api/v1/documents",
        headers=e2e_runtime.headers("user-b"),
    )
    assert user_a_listed.status_code == 200
    assert user_b_listed.status_code == 200
    assert {item["id"] for item in user_a_listed.json()["documents"]} == {
        user_a_document["document_id"]
    }
    assert {item["id"] for item in user_b_listed.json()["documents"]} == {
        user_b_document["document_id"]
    }
    assert "storage_key" not in str(user_a_listed.json())
    assert "storage_backend" not in str(user_a_listed.json())

    forbidden_question = e2e_runtime.client.post(
        "/api/v1/questions",
        json={"question": "beta", "document_ids": [user_b_document["document_id"]]},
        headers=e2e_runtime.headers("user-a"),
    )
    assert forbidden_question.status_code == 404
    assert forbidden_question.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
    assert (
        _retrieve_qdrant(
            e2e_runtime,
            "beta",
            user_b_document["document_id"],
            user_id=str(user_a.id),
        )
        == []
    )

    user_a_question = e2e_runtime.client.post(
        "/api/v1/questions",
        json={"question": "alpha", "document_ids": [user_a_document["document_id"]]},
        headers=e2e_runtime.headers("user-a"),
    )
    user_b_question = e2e_runtime.client.post(
        "/api/v1/questions",
        json={"question": "beta", "document_ids": [user_b_document["document_id"]]},
        headers=e2e_runtime.headers("user-b"),
    )
    assert user_a_question.status_code == 200
    assert user_a_question.json()["status"] == "answered"
    assert user_b_question.status_code == 200
    assert user_b_question.json()["status"] == "answered"

    user_a_session = _submit_message(
        e2e_runtime,
        data=[("message", "alpha"), ("document_ids", user_a_document["document_id"])],
        subject="user-a",
    )
    user_b_session = _submit_message(
        e2e_runtime,
        data=[("message", "beta"), ("document_ids", user_b_document["document_id"])],
        subject="user-b",
    )
    user_b_follow_up = _submit_message(
        e2e_runtime,
        data=[
            ("message", "beta follow up"),
            ("session_id", user_b_session["session_id"]),
            ("document_ids", user_b_document["document_id"]),
        ],
        subject="user-b",
    )
    assert user_b_follow_up["session_id"] == user_b_session["session_id"]

    forbidden_session_read = e2e_runtime.client.get(
        f"/api/v1/sessions/{user_b_session['session_id']}",
        headers=e2e_runtime.headers("user-a"),
    )
    forbidden_session_continue = e2e_runtime.client.post(
        "/api/v1/messages",
        data={
            "message": "try to continue someone else's chat",
            "session_id": user_b_session["session_id"],
        },
        headers=e2e_runtime.headers("user-a"),
    )
    forbidden_workflow = e2e_runtime.client.get(
        f"/api/v1/workflows/{user_b_session['workflow_id']}",
        headers=e2e_runtime.headers("user-a"),
    )
    own_workflow = e2e_runtime.client.get(
        f"/api/v1/workflows/{user_b_session['workflow_id']}",
        headers=e2e_runtime.headers("user-b"),
    )
    assert forbidden_session_read.status_code == 404
    assert forbidden_session_continue.status_code == 404
    assert forbidden_workflow.status_code == 404
    assert own_workflow.status_code == 200
    assert own_workflow.json()["workflow_id"] == user_b_session["workflow_id"]
    assert user_a_session["status"] == "answered"
    assert user_b_session["status"] == "answered"


def test_project_library_documents_are_project_scoped(
    e2e_runtime: E2ERuntime,
) -> None:
    alpha_organization = _create_organization(e2e_runtime, slug="phase2-alpha")
    beta_organization = _create_organization(e2e_runtime, slug="phase2-beta")
    alpha_project = _create_project(
        e2e_runtime,
        alpha_organization["id"],
        name="Alpha Project",
    )
    beta_project = _create_project(
        e2e_runtime,
        beta_organization["id"],
        name="Beta Project",
    )
    alpha = _upload_project_library_document(
        e2e_runtime,
        project_id=alpha_project["id"],
        filename="alpha.md",
        content=b"# Alpha\nalpha project evidence.\n",
        content_type="text/markdown",
    )
    beta = _upload_project_library_document(
        e2e_runtime,
        project_id=beta_project["id"],
        filename="beta.md",
        content=b"# Beta\nbeta project evidence.\n",
        content_type="text/markdown",
    )

    assert alpha["status"] == DocumentStatus.INDEXED.value
    assert beta["status"] == DocumentStatus.INDEXED.value
    assert alpha["document_scope"] == DocumentScope.PROJECT_LIBRARY.value
    assert alpha["session_id"] is None
    assert "storage_key" not in alpha

    alpha_document = asyncio.run(
        e2e_runtime.scalar(
            select(DocumentModel).where(
                DocumentModel.id == uuid.UUID(alpha["document_id"])
            )
        )
    )
    alpha_file = _file_metadata(e2e_runtime, alpha["document_id"])
    assert alpha_document is not None
    assert alpha_document.organization_id == uuid.UUID(alpha_organization["id"])
    assert alpha_document.project_id == uuid.UUID(alpha_project["id"])
    assert alpha_document.document_scope == DocumentScope.PROJECT_LIBRARY.value
    assert alpha_document.session_id is None
    assert alpha_file.storage_key.startswith(
        f"organizations/{alpha_organization['id']}/projects/{alpha_project['id']}/"
        "library/documents/"
    )
    assert e2e_runtime.storage.exists(alpha_file.storage_key) is True
    qdrant_payloads = _qdrant_payloads_for_document(
        e2e_runtime,
        document_id=alpha["document_id"],
    )
    assert qdrant_payloads
    assert {
        (
            payload["organization_id"],
            payload["project_id"],
            payload["document_scope"],
        )
        for payload in qdrant_payloads
    } == {
        (
            alpha_organization["id"],
            alpha_project["id"],
            DocumentScope.PROJECT_LIBRARY.value,
        )
    }

    alpha_list = e2e_runtime.client.get(
        f"/api/v1/projects/{alpha_project['id']}/library/documents",
        headers=e2e_runtime.headers("user-a"),
    )
    beta_list = e2e_runtime.client.get(
        f"/api/v1/projects/{beta_project['id']}/library/documents",
        headers=e2e_runtime.headers("user-a"),
    )
    forbidden_list = e2e_runtime.client.get(
        f"/api/v1/projects/{alpha_project['id']}/library/documents",
        headers=e2e_runtime.headers("user-b"),
    )
    assert alpha_list.status_code == 200
    assert [item["document_id"] for item in alpha_list.json()["documents"]] == [
        alpha["document_id"]
    ]
    assert beta_list.status_code == 200
    assert [item["document_id"] for item in beta_list.json()["documents"]] == [
        beta["document_id"]
    ]
    assert forbidden_list.status_code == 404
    assert (
        e2e_runtime.client.get(
            f"/api/v1/projects/{beta_project['id']}/library/documents/"
            f"{alpha['document_id']}",
            headers=e2e_runtime.headers("user-a"),
        ).status_code
        == 404
    )
    assert (
        e2e_runtime.client.get(
            f"/api/v1/projects/{beta_project['id']}/library/documents/"
            f"{alpha['document_id']}/download",
            headers=e2e_runtime.headers("user-a"),
        ).status_code
        == 404
    )
    assert (
        e2e_runtime.client.delete(
            f"/api/v1/projects/{beta_project['id']}/library/documents/"
            f"{alpha['document_id']}",
            headers=e2e_runtime.headers("user-a"),
        ).status_code
        == 404
    )

    assert _retrieve_project_qdrant(
        e2e_runtime,
        "alpha",
        document_id=alpha["document_id"],
        organization_id=alpha_organization["id"],
        project_id=alpha_project["id"],
        document_scope=DocumentScope.PROJECT_LIBRARY.value,
    )
    assert (
        _retrieve_project_qdrant(
            e2e_runtime,
            "alpha",
            document_id=alpha["document_id"],
            organization_id=beta_organization["id"],
            project_id=beta_project["id"],
            document_scope=DocumentScope.PROJECT_LIBRARY.value,
        )
        == []
    )
    assert (
        _retrieve_project_qdrant(
            e2e_runtime,
            "alpha",
            document_id=alpha["document_id"],
            organization_id=alpha_organization["id"],
            project_id=alpha_project["id"],
            document_scope=DocumentScope.CHAT_ATTACHMENT.value,
        )
        == []
    )


def test_project_chat_attachments_are_session_scoped(
    e2e_runtime: E2ERuntime,
) -> None:
    organization = _create_organization(e2e_runtime, slug="phase3-chat")
    project = _create_project(
        e2e_runtime,
        organization["id"],
        name="Chat Project",
    )
    library = _upload_project_library_document(
        e2e_runtime,
        project_id=project["id"],
        filename="library.md",
        content=b"# Library\nalpha project library evidence.\n",
        content_type="text/markdown",
    )
    _assert_indexed(library)

    first_session = _create_project_session(e2e_runtime, project_id=project["id"])
    second_session = _create_project_session(e2e_runtime, project_id=project["id"])
    response = _submit_project_message(
        e2e_runtime,
        project_id=project["id"],
        session_id=first_session["id"],
        message="What alpha and beta evidence is available?",
        files={
            "files": (
                "chat.txt",
                b"beta chat attachment evidence.\n",
                "text/plain",
            )
        },
    )

    assert response["session_id"] == first_session["id"]
    assert response["workflow_id"]
    assert response["attachments"]
    attachment = response["attachments"][0]
    attachment_document = asyncio.run(
        e2e_runtime.scalar(
            select(DocumentModel).where(
                DocumentModel.id == uuid.UUID(attachment["document_id"])
            )
        )
    )
    attachment_file = _file_metadata(e2e_runtime, attachment["document_id"])
    assert attachment_document is not None
    assert attachment_document.organization_id == uuid.UUID(organization["id"])
    assert attachment_document.project_id == uuid.UUID(project["id"])
    assert attachment_document.session_id == uuid.UUID(first_session["id"])
    assert attachment_document.document_scope == DocumentScope.CHAT_ATTACHMENT.value
    expected_key = (
        f"organizations/{organization['id']}/projects/{project['id']}/"
        f"sessions/{first_session['id']}/attachments/{attachment['document_id']}/"
        "source/content.txt"
    )
    assert attachment_file.storage_key == expected_key
    assert e2e_runtime.storage.exists(expected_key) is True

    payloads = _qdrant_payloads_for_document(
        e2e_runtime,
        document_id=attachment["document_id"],
    )
    assert payloads
    assert {
        (
            payload["document_id"],
            payload["organization_id"],
            payload["project_id"],
            payload["document_scope"],
            payload["session_id"],
        )
        for payload in payloads
    } == {
        (
            attachment["document_id"],
            organization["id"],
            project["id"],
            DocumentScope.CHAT_ATTACHMENT.value,
            first_session["id"],
        )
    }
    assert {source["document_id"] for source in response["sources"]} >= {
        library["document_id"],
        attachment["document_id"],
    }
    assert _retrieve_project_session_qdrant(
        e2e_runtime,
        "beta",
        organization_id=organization["id"],
        project_id=project["id"],
        session_id=first_session["id"],
    )
    assert (
        _retrieve_project_session_qdrant(
            e2e_runtime,
            "beta",
            organization_id=organization["id"],
            project_id=project["id"],
            session_id=second_session["id"],
        )
        == []
    )


def _user_record(runtime: E2ERuntime, subject: str) -> User:
    user = asyncio.run(
        runtime.scalar(select(User).where(User.external_subject == subject))
    )
    assert user is not None
    return user


def _file_metadata(runtime: E2ERuntime, document_id: str) -> FileMetadata:
    file_metadata = asyncio.run(
        runtime.scalar(
            select(FileMetadata).where(
                FileMetadata.document_id == uuid.UUID(document_id)
            )
        )
    )
    assert file_metadata is not None
    return file_metadata


def _upload(
    runtime: E2ERuntime,
    *,
    filename: str,
    content: bytes,
    content_type: str,
    subject: str = "user-a",
) -> dict[str, Any]:
    response = runtime.client.post(
        "/api/v1/documents",
        files={"file": (filename, content, content_type)},
        headers=runtime.headers(subject),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_organization(
    runtime: E2ERuntime,
    *,
    slug: str,
    subject: str = "user-a",
) -> dict[str, Any]:
    response = runtime.client.post(
        "/api/v1/organizations",
        json={"name": f"{slug.title()} Organization", "slug": slug},
        headers=runtime.headers(subject),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_project(
    runtime: E2ERuntime,
    organization_id: str,
    *,
    name: str,
    subject: str = "user-a",
) -> dict[str, Any]:
    response = runtime.client.post(
        f"/api/v1/organizations/{organization_id}/projects",
        json={"name": name},
        headers=runtime.headers(subject),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload_project_library_document(
    runtime: E2ERuntime,
    *,
    project_id: str,
    filename: str,
    content: bytes,
    content_type: str,
    subject: str = "user-a",
) -> dict[str, Any]:
    response = runtime.client.post(
        f"/api/v1/projects/{project_id}/library/documents",
        files={"file": (filename, content, content_type)},
        headers=runtime.headers(subject),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_project_session(
    runtime: E2ERuntime,
    *,
    project_id: str,
    subject: str = "user-a",
) -> dict[str, Any]:
    response = runtime.client.post(
        f"/api/v1/projects/{project_id}/sessions",
        json={"title": "E2E chat"},
        headers=runtime.headers(subject),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _submit_project_message(
    runtime: E2ERuntime,
    *,
    project_id: str,
    session_id: str,
    message: str,
    files: dict[str, tuple[str, bytes, str]] | None = None,
    subject: str = "user-a",
) -> dict[str, Any]:
    response = runtime.client.post(
        f"/api/v1/projects/{project_id}/sessions/{session_id}/messages",
        data={"message": message},
        files=files,
        headers=runtime.headers(subject),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _assert_indexed(payload: dict[str, Any]) -> None:
    assert payload["status"] == DocumentStatus.INDEXED.value, (
        payload.get("indexing_error_code"),
        payload.get("indexing_error_message"),
        payload,
    )


def _submit_message(
    runtime: E2ERuntime,
    *,
    data: list[tuple[str, str]],
    subject: str = "user-a",
) -> dict[str, Any]:
    form_data: dict[str, str | list[str]] = {}
    for key, value in data:
        existing = form_data.get(key)
        if existing is None:
            form_data[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            form_data[key] = [existing, value]

    response = runtime.client.post(
        "/api/v1/messages",
        data=form_data,
        headers=runtime.headers(subject),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _retrieve_qdrant(
    runtime: E2ERuntime,
    query: str,
    document_id: str,
    user_id: str,
):
    return Retriever(
        embedding_provider=KeywordEmbeddingProvider(),
        vector_store=_vector_store(runtime.collection_name),
    ).retrieve(
        query,
        top_k=5,
        filters={"document_id": document_id, "user_id": user_id},
    )


def _qdrant_payloads_for_document(
    runtime: E2ERuntime,
    *,
    document_id: str,
) -> list[dict[str, Any]]:
    client = QdrantClient(url=runtime.qdrant_url)
    try:
        points, _next_page = client.scroll(
            collection_name=runtime.collection_name,
            scroll_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="document_id",
                        match=qdrant_models.MatchValue(value=document_id),
                    )
                ]
            ),
            limit=10,
            with_payload=True,
            with_vectors=False,
        )
    finally:
        client.close()
    return [dict(point.payload or {}) for point in points]


def _retrieve_project_qdrant(
    runtime: E2ERuntime,
    query: str,
    *,
    document_id: str,
    organization_id: str,
    project_id: str,
    document_scope: str,
):
    return Retriever(
        embedding_provider=KeywordEmbeddingProvider(),
        vector_store=_vector_store(runtime.collection_name),
    ).retrieve(
        query,
        top_k=5,
        filters={
            "document_id": document_id,
            "organization_id": organization_id,
            "project_id": project_id,
            "document_scope": document_scope,
        },
    )


def _retrieve_project_session_qdrant(
    runtime: E2ERuntime,
    query: str,
    *,
    organization_id: str,
    project_id: str,
    session_id: str,
):
    return Retriever(
        embedding_provider=KeywordEmbeddingProvider(),
        vector_store=_vector_store(runtime.collection_name),
    ).retrieve(
        query,
        top_k=5,
        filters={
            "organization_id": organization_id,
            "project_id": project_id,
            "document_scope": DocumentScope.CHAT_ATTACHMENT.value,
            "session_id": session_id,
        },
    )


def _dev_token(subject: str) -> str:
    return jwt.encode(
        {
            "iss": AUTH_ISSUER,
            "aud": AUTH_AUDIENCE,
            "sub": subject,
            "email": f"{subject}@example.test",
            "exp": datetime.now(UTC) + timedelta(minutes=15),
        },
        AUTH_SECRET,
        algorithm="HS256",
    )


def _vector_store(collection_name: str) -> QdrantVectorStore:
    assert TEST_QDRANT_URL is not None
    return QdrantVectorStore(
        collection_name=collection_name,
        dimension=KeywordEmbeddingProvider.dimension,
        url=TEST_QDRANT_URL,
        wait=True,
    )


def _require_e2e_environment() -> None:
    if not E2E_ENABLED:
        pytest.skip("Set RASTIN_AI_E2E=1 to run isolated E2E tests.")
    if not TEST_DATABASE_URL:
        pytest.skip("RASTIN_AI_TEST_DATABASE_URL is required for E2E tests.")
    if not _is_safe_test_database_url(TEST_DATABASE_URL):
        pytest.skip(
            "RASTIN_AI_TEST_DATABASE_URL must point to a database ending in _test.",
        )
    if not TEST_QDRANT_URL:
        pytest.skip("RASTIN_AI_TEST_QDRANT_URL is required for E2E tests.")


def _is_safe_test_database_url(database_url: str | None) -> bool:
    if not database_url:
        return False
    try:
        database_name = make_url(database_url).database
    except ArgumentError:
        return False
    return bool(database_name and database_name.endswith("_test"))


def _reset_database(database_url: str) -> None:
    asyncio.run(_reset_database_async(database_url))


async def _reset_database_async(database_url: str) -> None:
    engine = create_database_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
            await connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
    finally:
        await engine.dispose()


def _run_migrations() -> None:
    from rastin_ai.core.config import get_settings

    get_settings.cache_clear()
    config = Config(PROJECT_ROOT / "alembic.ini")
    command.upgrade(config, "head")
    get_settings.cache_clear()


def _delete_qdrant_collection(qdrant_url: str, collection_name: str) -> None:
    client = QdrantClient(url=qdrant_url)
    try:
        if client.collection_exists(collection_name):
            client.delete_collection(collection_name=collection_name)
    finally:
        client.close()


async def _dispose_cached_engine() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def _reset_app_modules() -> None:
    from rastin_ai.core.config import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
