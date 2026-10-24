"""File guide.

- Use: Contains unit tests for question-answering service behavior.
- Usage: Run this file with pytest when checking direct attachment context.
- Duties: Uses fakes to verify attachment text can answer without vector retrieval.
- Depends on: Project modules: rastin_ai.services.questions.
"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from rastin_ai.database.enums import DocumentStatus, WorkflowExecutionStatus
from rastin_ai.rag.context.builder import ContextBuilder
from rastin_ai.rag.models import Chunk, Document, RetrievedChunk
from rastin_ai.repositories.workflow_execution import WorkflowExecutionRecord
from rastin_ai.services.documents import (
    DocumentNotFoundError,
    DocumentRecord,
    DocumentUpload,
)
from rastin_ai.services.questions import (
    QUESTION_STATUS_INDEXING_FAILED,
    QUESTION_STATUS_INSUFFICIENT_EVIDENCE,
    QUESTION_STATUS_NO_EVIDENCE,
    QUESTION_STATUS_NOT_READY,
    ProjectRetrievalScope,
    QuestionAttachment,
    QuestionInput,
    RAGQuestionAnsweringService,
)

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
SECOND_DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
THIRD_DOCUMENT_ID = UUID("33333333-3333-4333-8333-333333333333")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
ORGANIZATION_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
PROJECT_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
SESSION_ID = UUID("99999999-9999-4999-8999-999999999999")
SECOND_SESSION_ID = UUID("88888888-8888-4888-8888-888888888888")
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class ExplodingRetriever:
    def retrieve(self, *_args, **_kwargs):
        raise AssertionError("Retriever should not run for direct attachment context.")


class FakeResponseGenerator:
    def __init__(self) -> None:
        self.tool_result = None
        self.call_count = 0
        self.last_generation_metadata = None

    def generate_response(self, **kwargs) -> str:
        self.call_count += 1
        self.tool_result = kwargs["tool_result"]
        self.last_generation_metadata = SimpleNamespace(
            model="fake-response-model",
            token_usage={"input_tokens": 9, "output_tokens": 5},
        )
        return "Amir has Python and FastAPI experience."


class FakeDocumentService:
    def __init__(self, documents: list[DocumentRecord] | None = None) -> None:
        self.documents = documents or []

    async def upload_document(self, upload: DocumentUpload) -> DocumentRecord:
        raise AssertionError("Document upload is not part of this test.")

    async def list_documents(self) -> list[DocumentRecord]:
        return self.documents

    async def ensure_documents_exist(self, document_ids: list[UUID]) -> None:
        await self.get_documents(document_ids)

    async def get_documents(self, document_ids: list[UUID]) -> list[DocumentRecord]:
        known = {document.document_id: document for document in self.documents}
        records = []
        for document_id in dict.fromkeys(document_ids):
            if document_id not in known:
                raise DocumentNotFoundError(document_id)
            records.append(known[document_id])
        return records


class FakeRetriever:
    def __init__(self, results_by_document_id: dict[str, list[RetrievedChunk]]) -> None:
        self.results_by_document_id = results_by_document_id
        self.calls = []

    def retrieve(self, query: str, *, top_k: int = 5, filters=None, **kwargs):
        self.calls.append({"query": query, "top_k": top_k, "filters": filters})
        document_id = None if filters is None else filters.get("document_id")
        return list(self.results_by_document_id.get(str(document_id), []))[:top_k]


class ProjectScopeRetriever:
    def __init__(
        self, library_text: str = "Project library says launch code is apollo."
    ) -> None:
        self.calls = []
        self.library_text = library_text

    def retrieve(self, query: str, *, top_k: int = 5, filters=None, **kwargs):
        _ = query
        _ = top_k
        _ = kwargs
        self.calls.append(filters)
        if filters == {
            "organization_id": str(ORGANIZATION_ID),
            "project_id": str(PROJECT_ID),
            "document_scope": "PROJECT_LIBRARY",
        }:
            return [
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    text=self.library_text,
                    filename="library.txt",
                    metadata={"document_scope": "PROJECT_LIBRARY"},
                )
            ]
        if filters == {
            "organization_id": str(ORGANIZATION_ID),
            "project_id": str(PROJECT_ID),
            "document_scope": "CHAT_ATTACHMENT",
            "session_id": str(SESSION_ID),
        }:
            return [
                _retrieved_chunk(
                    document_id=str(SECOND_DOCUMENT_ID),
                    text="Attachment says launch code is artemis.",
                    chunk_id="attachment-chunk",
                    filename="chat.txt",
                    metadata={
                        "document_scope": "CHAT_ATTACHMENT",
                        "session_id": str(SESSION_ID),
                    },
                )
            ]
        return []


class FakeWorkflowRepository:
    def __init__(self) -> None:
        self.created: list[WorkflowExecutionRecord] = []
        self.completed: list[tuple[UUID, dict | None]] = []
        self.failed: list[tuple[UUID, str]] = []
        self.trace_updates: list[tuple[UUID, str]] = []

    async def create(
        self,
        *,
        workflow_name: str,
        input_payload: dict | None = None,
        workflow_version: str | None = None,
        status: WorkflowExecutionStatus = WorkflowExecutionStatus.PENDING,
        user_id: UUID,
        session_id: UUID | None = None,
        organization_id: UUID | None = None,
        project_id: UUID | None = None,
    ) -> WorkflowExecutionRecord:
        record = WorkflowExecutionRecord(
            user_id=user_id,
            id=uuid4(),
            session_id=session_id or UUID("99999999-9999-4999-8999-999999999999"),
            workflow_name=workflow_name,
            workflow_version=workflow_version,
            status=status.value,
            input_payload=input_payload,
            output_payload=None,
            error_message=None,
            trace_id=None,
            started_at=NOW,
            finished_at=None,
            created_at=NOW,
            updated_at=NOW,
            organization_id=organization_id,
            project_id=project_id,
        )
        self.created.append(record)
        return record

    async def complete(
        self,
        workflow_id: UUID,
        *,
        user_id: UUID,
        output_payload: dict | None = None,
    ) -> WorkflowExecutionRecord:
        assert user_id == USER_ID
        self.completed.append((workflow_id, output_payload))
        return self.created[-1]

    async def fail(
        self,
        workflow_id: UUID,
        *,
        user_id: UUID,
        error_message: str,
    ) -> WorkflowExecutionRecord:
        assert user_id == USER_ID
        self.failed.append((workflow_id, error_message))
        return self.created[-1]

    async def set_trace_id(
        self,
        workflow_id: UUID,
        *,
        user_id: UUID,
        trace_id: str,
    ) -> WorkflowExecutionRecord:
        assert user_id == USER_ID
        self.trace_updates.append((workflow_id, trace_id))
        return self.created[-1]

    async def get_by_id(
        self,
        workflow_id: UUID,
        *,
        user_id: UUID,
    ) -> WorkflowExecutionRecord | None:
        _ = workflow_id
        _ = user_id
        return None

    async def list_recent(
        self,
        *,
        user_id: UUID,
        limit: int,
    ) -> list[WorkflowExecutionRecord]:
        _ = user_id
        _ = limit
        return []


def test_answer_uses_uploaded_attachment_text_before_vector_retrieval() -> None:
    asyncio.run(_run_attachment_context_test())


def test_answer_uses_attachment_documents_with_source_metadata() -> None:
    asyncio.run(_run_attachment_document_context_test())


def test_persisted_retrieval_is_filtered_by_logical_document_uuid() -> None:
    asyncio.run(_run_filtered_retrieval_test())


def test_multiple_selected_documents_retrieve_only_those_documents() -> None:
    asyncio.run(_run_multiple_document_scope_test())


def test_nonexistent_document_id_returns_validation_error() -> None:
    asyncio.run(_run_missing_document_test())


@pytest.mark.parametrize(
    "status",
    [DocumentStatus.UPLOADED.value, DocumentStatus.PROCESSING.value],
)
def test_unindexed_document_states_return_not_ready(status: str) -> None:
    asyncio.run(_run_not_ready_state_test(status))


def test_failed_document_state_returns_safe_indexing_failure() -> None:
    asyncio.run(_run_failed_state_test())


def test_no_retrieved_evidence_skips_generation() -> None:
    asyncio.run(_run_no_evidence_test())


def test_missing_document_scope_skips_unscoped_retrieval() -> None:
    asyncio.run(_run_missing_scope_test())


def test_insufficient_evidence_skips_generation_with_limitation() -> None:
    asyncio.run(_run_insufficient_evidence_test())


def test_citations_preserve_format_specific_metadata() -> None:
    asyncio.run(_run_citation_metadata_test())


def test_duplicate_chunks_do_not_inflate_final_context() -> None:
    asyncio.run(_run_duplicate_chunk_test())


def test_context_budget_is_enforced_before_generation() -> None:
    asyncio.run(_run_context_budget_test())


def test_citations_do_not_leak_storage_keys_or_paths() -> None:
    asyncio.run(_run_citation_leak_test())


def test_project_retrieval_uses_current_session_attachment_filters() -> None:
    asyncio.run(_run_project_retrieval_scope_test())


@pytest.mark.parametrize(
    ("question", "evidence"),
    [
        (
            "how many languges he can speak?",
            "LINGUE\nInglese: fluente\nItaliano: A2, in continuo miglioramento",
        ),
        (
            "How many languages does he speak?",
            "LINGUE\nInglese: fluente\nItaliano: A2, in continuo miglioramento",
        ),
        (
            "Which tongues can the candidate use?",
            "Fluent English; conversational Italian.",
        ),
    ],
)
def test_new_project_chat_generates_from_semantic_evidence_without_word_overlap(
    question: str, evidence: str
) -> None:
    asyncio.run(_run_project_semantic_evidence_test(question, evidence))


@pytest.mark.parametrize("context_max_chars", [None, 1])
def test_project_chat_without_usable_evidence_skips_generation(
    context_max_chars: int | None,
) -> None:
    asyncio.run(_run_project_no_evidence_test(context_max_chars))


def test_direct_rag_persists_observability_trace_id(monkeypatch) -> None:
    from test_observability import FakeLangfuseClient

    import rastin_ai.observability.langfuse as langfuse_observability

    fake_client = FakeLangfuseClient()
    monkeypatch.setattr(
        langfuse_observability,
        "_get_langfuse_client",
        lambda settings=None: fake_client,
    )

    asyncio.run(_run_trace_persistence_test())


async def _run_attachment_context_test() -> None:
    generator = FakeResponseGenerator()
    service = RAGQuestionAnsweringService(
        retriever=ExplodingRetriever(),
        context_builder=ContextBuilder(),
        response_generator=generator,
        document_service=FakeDocumentService(),
        user_id=USER_ID,
    )

    answer = await service.answer(
        QuestionInput(
            question="What technical skills does Amir have?",
            document_ids=[],
            attachments=(
                QuestionAttachment(
                    document_id=DOCUMENT_ID,
                    filename="cv.txt",
                    content_type="text/plain",
                    size_bytes=41,
                    status="stored",
                    text="Amir builds AI systems with Python and FastAPI.",
                ),
            ),
        )
    )

    assert answer.answer == "Amir has Python and FastAPI experience."
    assert answer.sources[0]["filename"] == "cv.txt"
    assert generator.tool_result["sources"][0]["filename"] == "cv.txt"
    assert "Python and FastAPI" in generator.tool_result["text"]
    assert answer.retrieved_contexts == (generator.tool_result["text"],)
    assert answer.model_name == "fake-response-model"
    assert answer.token_usage == {"input_tokens": 9, "output_tokens": 5}
    assert answer.workflow_details[0]["summary"] == (
        "1 file(s) stored. 1 uploaded file(s) used as direct answer context."
    )


async def _run_attachment_document_context_test() -> None:
    generator = FakeResponseGenerator()
    service = RAGQuestionAnsweringService(
        retriever=ExplodingRetriever(),
        context_builder=ContextBuilder(),
        response_generator=generator,
        document_service=FakeDocumentService(),
        user_id=USER_ID,
    )

    answer = await service.answer(
        QuestionInput(
            question="Who appears in the sheet?",
            document_ids=[],
            attachments=(
                QuestionAttachment(
                    document_id=DOCUMENT_ID,
                    filename="people.csv",
                    content_type="text/csv",
                    size_bytes=20,
                    status="indexed",
                    documents=(
                        Document(
                            id="attachment-doc",
                            text="Columns: name\nRow 2: name=Alice",
                            source="attachment:people.csv",
                            metadata={
                                "source": "attachment:people.csv",
                                "filename": "people.csv",
                                "file_type": "csv",
                                "document_id": str(DOCUMENT_ID),
                                "location_type": "row_range",
                                "source_location": "rows:2-2",
                                "row_start": 2,
                                "row_end": 2,
                                "columns": ["name"],
                            },
                        ),
                    ),
                ),
            ),
        )
    )

    assert answer.sources[0]["source_location"] == "rows:2-2"
    assert answer.sources[0]["row_start"] == 2
    assert generator.tool_result["sources"][0]["columns"] == ["name"]


async def _run_filtered_retrieval_test() -> None:
    generator = FakeResponseGenerator()
    retriever = FakeRetriever(
        {
            str(DOCUMENT_ID): [
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    text="alpha evidence",
                    filename="report.pdf",
                    metadata={"location_type": "page", "page_number": 2},
                )
            ],
        }
    )
    service = _persisted_service(retriever, generator)

    answer = await service.answer(
        QuestionInput(question="What does alpha say?", document_ids=[DOCUMENT_ID])
    )

    assert retriever.calls == [
        {
            "query": "What does alpha say?",
            "top_k": 5,
            "filters": {"document_id": str(DOCUMENT_ID), "user_id": str(USER_ID)},
        }
    ]
    assert answer.status == "answered"
    assert answer.citations[0]["document_id"] == str(DOCUMENT_ID)
    assert generator.call_count == 1


async def _run_multiple_document_scope_test() -> None:
    generator = FakeResponseGenerator()
    retriever = FakeRetriever(
        {
            str(DOCUMENT_ID): [
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    chunk_id="chunk-one",
                    text="alpha one",
                )
            ],
            str(SECOND_DOCUMENT_ID): [
                _retrieved_chunk(
                    document_id=str(SECOND_DOCUMENT_ID),
                    chunk_id="chunk-two",
                    text="alpha two",
                )
            ],
            str(THIRD_DOCUMENT_ID): [
                _retrieved_chunk(document_id=str(THIRD_DOCUMENT_ID), text="alpha leak")
            ],
        }
    )
    service = _persisted_service(retriever, generator)

    answer = await service.answer(
        QuestionInput(
            question="alpha",
            document_ids=[DOCUMENT_ID, SECOND_DOCUMENT_ID],
        )
    )

    assert [call["filters"]["document_id"] for call in retriever.calls] == [
        str(DOCUMENT_ID),
        str(SECOND_DOCUMENT_ID),
    ]
    assert [call["filters"]["user_id"] for call in retriever.calls] == [
        str(USER_ID),
        str(USER_ID),
    ]
    assert {citation["document_id"] for citation in answer.citations} == {
        str(DOCUMENT_ID),
        str(SECOND_DOCUMENT_ID),
    }


async def _run_missing_document_test() -> None:
    service = _persisted_service(FakeRetriever({}), FakeResponseGenerator())

    with pytest.raises(DocumentNotFoundError):
        await service.answer(
            QuestionInput(question="alpha", document_ids=[THIRD_DOCUMENT_ID])
        )


async def _run_not_ready_state_test(document_status: str) -> None:
    generator = FakeResponseGenerator()
    retriever = FakeRetriever({})
    service = _persisted_service(
        retriever,
        generator,
        documents=[_document_record(status=document_status)],
    )

    answer = await service.answer(
        QuestionInput(question="alpha", document_ids=[DOCUMENT_ID])
    )

    assert answer.status == QUESTION_STATUS_NOT_READY
    assert "not ready" in answer.answer
    assert retriever.calls == []
    assert generator.call_count == 0


async def _run_failed_state_test() -> None:
    generator = FakeResponseGenerator()
    retriever = FakeRetriever({})
    service = _persisted_service(
        retriever,
        generator,
        documents=[
            _document_record(
                status=DocumentStatus.FAILED.value,
                indexing_error_code="MALFORMED_JSON",
                indexing_error_message="internal/path/secret.json",
            )
        ],
    )

    answer = await service.answer(
        QuestionInput(question="alpha", document_ids=[DOCUMENT_ID])
    )

    assert answer.status == QUESTION_STATUS_INDEXING_FAILED
    assert "MALFORMED_JSON" in (answer.message or "")
    assert "secret.json" not in (answer.message or "")
    assert retriever.calls == []
    assert generator.call_count == 0


async def _run_no_evidence_test() -> None:
    generator = FakeResponseGenerator()
    retriever = FakeRetriever({str(DOCUMENT_ID): []})
    service = _persisted_service(retriever, generator)

    answer = await service.answer(
        QuestionInput(question="alpha", document_ids=[DOCUMENT_ID])
    )

    assert answer.status == QUESTION_STATUS_NO_EVIDENCE
    assert answer.citations == ()
    assert generator.call_count == 0


async def _run_missing_scope_test() -> None:
    generator = FakeResponseGenerator()
    retriever = FakeRetriever({})
    service = _persisted_service(retriever, generator)

    answer = await service.answer(QuestionInput(question="alpha", document_ids=[]))

    assert answer.status == QUESTION_STATUS_NO_EVIDENCE
    assert "explicit logical document IDs" in (answer.message or "")
    assert retriever.calls == []
    assert generator.call_count == 0


async def _run_insufficient_evidence_test() -> None:
    generator = FakeResponseGenerator()
    retriever = FakeRetriever(
        {
            str(DOCUMENT_ID): [
                _retrieved_chunk(document_id=str(DOCUMENT_ID), text="beta")
            ]
        }
    )
    service = _persisted_service(retriever, generator)

    answer = await service.answer(
        QuestionInput(question="zebra", document_ids=[DOCUMENT_ID])
    )

    assert answer.status == QUESTION_STATUS_INSUFFICIENT_EVIDENCE
    assert "insufficient" in answer.answer
    assert len(answer.citations) == 1
    assert generator.call_count == 0


async def _run_citation_metadata_test() -> None:
    generator = FakeResponseGenerator()
    retriever = FakeRetriever(
        {
            str(DOCUMENT_ID): [
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    chunk_id="pdf-chunk",
                    text="alpha pdf",
                    filename="report.pdf",
                    metadata={"location_type": "page", "page_number": 3},
                ),
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    chunk_id="csv-chunk",
                    text="alpha csv",
                    filename="people.csv",
                    file_type="csv",
                    metadata={
                        "location_type": "row_range",
                        "row_start": 2,
                        "row_end": 5,
                        "columns": ["name", "role"],
                    },
                ),
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    chunk_id="xlsx-chunk",
                    text="alpha xlsx",
                    filename="budget.xlsx",
                    file_type="xlsx",
                    metadata={
                        "location_type": "sheet_rows",
                        "sheet_name": "Summary",
                        "row_start": 2,
                        "row_end": 4,
                    },
                ),
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    chunk_id="json-chunk",
                    text="alpha json",
                    filename="data.json",
                    file_type="json",
                    metadata={
                        "location_type": "json_path",
                        "json_path": "$.items",
                    },
                ),
            ]
        }
    )
    service = _persisted_service(retriever, generator)

    answer = await service.answer(
        QuestionInput(question="alpha", document_ids=[DOCUMENT_ID])
    )

    citations = {citation["chunk_id"]: citation for citation in answer.citations}
    assert citations["pdf-chunk"]["page_number"] == 3
    assert citations["csv-chunk"]["row_start"] == 2
    assert citations["csv-chunk"]["columns"] == ["name", "role"]
    assert citations["xlsx-chunk"]["sheet_name"] == "Summary"
    assert citations["json-chunk"]["json_path"] == "$.items"


async def _run_duplicate_chunk_test() -> None:
    generator = FakeResponseGenerator()
    duplicate_metadata = {"location_type": "page", "page_number": 1}
    retriever = FakeRetriever(
        {
            str(DOCUMENT_ID): [
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    chunk_id="chunk-a",
                    text="alpha repeated evidence",
                    metadata=duplicate_metadata,
                ),
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    chunk_id="chunk-b",
                    text="alpha repeated evidence",
                    metadata=duplicate_metadata,
                ),
            ]
        }
    )
    service = _persisted_service(retriever, generator)

    answer = await service.answer(
        QuestionInput(question="alpha", document_ids=[DOCUMENT_ID])
    )

    assert len(answer.citations) == 1
    assert generator.tool_result["text"].count("alpha repeated evidence") == 1


async def _run_context_budget_test() -> None:
    generator = FakeResponseGenerator()
    retriever = FakeRetriever(
        {
            str(DOCUMENT_ID): [
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    chunk_id="chunk-one",
                    text="alpha short evidence",
                ),
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    chunk_id="chunk-two",
                    text="alpha " + "long " * 40,
                ),
            ]
        }
    )
    service = _persisted_service(
        retriever,
        generator,
        context_builder=ContextBuilder(max_chars=140),
    )

    answer = await service.answer(
        QuestionInput(question="alpha", document_ids=[DOCUMENT_ID])
    )

    assert [citation["chunk_id"] for citation in answer.citations] == ["chunk-one"]
    assert "chunk-two" not in str(generator.tool_result)


async def _run_citation_leak_test() -> None:
    generator = FakeResponseGenerator()
    retriever = FakeRetriever(
        {
            str(DOCUMENT_ID): [
                _retrieved_chunk(
                    document_id=str(DOCUMENT_ID),
                    text="alpha evidence",
                    filename="safe.pdf",
                    source="files/11111111-1111-4111-8111-111111111111/content.pdf",
                    metadata={
                        "location_type": "page",
                        "page_number": 1,
                        "storage_key": "files/secret/content.pdf",
                    },
                )
            ]
        }
    )
    service = _persisted_service(retriever, generator)

    answer = await service.answer(
        QuestionInput(question="alpha", document_ids=[DOCUMENT_ID])
    )

    citation_payload = str(answer.citations[0])
    assert "files/" not in citation_payload
    assert "storage_key" not in citation_payload
    assert "content.pdf" not in citation_payload


async def _run_trace_persistence_test() -> None:
    generator = FakeResponseGenerator()
    workflow_repository = FakeWorkflowRepository()
    retriever = FakeRetriever(
        {
            str(DOCUMENT_ID): [
                _retrieved_chunk(document_id=str(DOCUMENT_ID), text="alpha evidence")
            ]
        }
    )
    service = _persisted_service(
        retriever,
        generator,
        workflow_repository=workflow_repository,
    )

    answer = await service.answer(
        QuestionInput(question="alpha", document_ids=[DOCUMENT_ID])
    )

    assert answer.workflow_id == workflow_repository.created[0].id
    assert workflow_repository.trace_updates == [
        (workflow_repository.created[0].id, "trace-test")
    ]


async def _run_project_retrieval_scope_test() -> None:
    generator = FakeResponseGenerator()
    retriever = ProjectScopeRetriever()
    workflow_repository = FakeWorkflowRepository()
    service = _persisted_service(
        retriever,
        generator,
        workflow_repository=workflow_repository,
    )

    answer = await service.answer(
        QuestionInput(
            question="What is the launch code?",
            document_ids=[],
            session_id=SESSION_ID,
            project_retrieval_scope=ProjectRetrievalScope(
                organization_id=ORGANIZATION_ID,
                project_id=PROJECT_ID,
                session_id=SESSION_ID,
            ),
        )
    )
    second_chat_answer = await service.answer(
        QuestionInput(
            question="What is the launch code?",
            document_ids=[],
            session_id=SECOND_SESSION_ID,
            project_retrieval_scope=ProjectRetrievalScope(
                organization_id=ORGANIZATION_ID,
                project_id=PROJECT_ID,
                session_id=SECOND_SESSION_ID,
            ),
        )
    )

    assert answer.status == "answered"
    assert {source["document_id"] for source in answer.sources} == {
        str(DOCUMENT_ID),
        str(SECOND_DOCUMENT_ID),
    }
    assert second_chat_answer.status == "answered"
    assert {source["document_id"] for source in second_chat_answer.sources} == {
        str(DOCUMENT_ID),
    }
    assert {
        "organization_id": str(ORGANIZATION_ID),
        "project_id": str(PROJECT_ID),
        "document_scope": "CHAT_ATTACHMENT",
        "session_id": str(SECOND_SESSION_ID),
    } in retriever.calls
    assert workflow_repository.created[0].organization_id == ORGANIZATION_ID
    assert workflow_repository.created[0].project_id == PROJECT_ID


async def _run_project_semantic_evidence_test(question: str, evidence: str) -> None:
    generator = FakeResponseGenerator()
    retriever = ProjectScopeRetriever(library_text=evidence)
    service = _persisted_service(retriever, generator)

    answer = await service.answer(
        QuestionInput(
            question=question,
            document_ids=[],
            session_id=SECOND_SESSION_ID,
            project_retrieval_scope=ProjectRetrievalScope(
                organization_id=ORGANIZATION_ID,
                project_id=PROJECT_ID,
                session_id=SECOND_SESSION_ID,
            ),
        )
    )

    assert answer.status == "answered"
    assert generator.call_count == 1
    assert evidence in generator.tool_result["text"]
    assert {source["document_id"] for source in answer.sources} == {str(DOCUMENT_ID)}
    assert {citation["document_id"] for citation in answer.citations} == {
        str(DOCUMENT_ID)
    }
    assert retriever.calls == [
        {
            "organization_id": str(ORGANIZATION_ID),
            "project_id": str(PROJECT_ID),
            "document_scope": "PROJECT_LIBRARY",
        },
        {
            "organization_id": str(ORGANIZATION_ID),
            "project_id": str(PROJECT_ID),
            "document_scope": "CHAT_ATTACHMENT",
            "session_id": str(SECOND_SESSION_ID),
        },
    ]


async def _run_project_no_evidence_test(context_max_chars: int | None) -> None:
    generator = FakeResponseGenerator()
    retriever = (
        FakeRetriever({}) if context_max_chars is None else ProjectScopeRetriever()
    )
    service = _persisted_service(
        retriever,
        generator,
        context_builder=ContextBuilder(max_chars=context_max_chars),
    )

    answer = await service.answer(
        QuestionInput(
            question="How many languages does he speak?",
            document_ids=[],
            session_id=SECOND_SESSION_ID,
            project_retrieval_scope=ProjectRetrievalScope(
                organization_id=ORGANIZATION_ID,
                project_id=PROJECT_ID,
                session_id=SECOND_SESSION_ID,
            ),
        )
    )

    assert answer.status == QUESTION_STATUS_NO_EVIDENCE
    assert answer.citations == ()
    assert answer.sources == ()
    assert generator.call_count == 0


def _persisted_service(
    retriever,
    generator: FakeResponseGenerator,
    *,
    documents: list[DocumentRecord] | None = None,
    context_builder: ContextBuilder | None = None,
    workflow_repository: FakeWorkflowRepository | None = None,
) -> RAGQuestionAnsweringService:
    return RAGQuestionAnsweringService(
        retriever=retriever,
        context_builder=context_builder or ContextBuilder(),
        response_generator=generator,
        document_service=FakeDocumentService(
            documents
            or [
                _document_record(document_id=DOCUMENT_ID),
                _document_record(document_id=SECOND_DOCUMENT_ID),
            ]
        ),
        workflow_repository=workflow_repository,
        user_id=USER_ID,
    )


def _document_record(
    *,
    document_id: UUID = DOCUMENT_ID,
    filename: str = "report.pdf",
    status: str = DocumentStatus.INDEXED.value,
    indexing_error_code: str | None = None,
    indexing_error_message: str | None = None,
) -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        filename=filename,
        content_type="application/pdf",
        status=status,
        created_at=NOW,
        size_bytes=100,
        indexing_error_code=indexing_error_code,
        indexing_error_message=indexing_error_message,
    )


def _retrieved_chunk(
    *,
    document_id: str,
    text: str,
    chunk_id: str = "chunk-1",
    filename: str = "report.pdf",
    file_type: str = "pdf",
    source: str = "files/internal/content.pdf",
    metadata: dict | None = None,
    score: float = 0.91,
) -> RetrievedChunk:
    chunk_metadata = {
        "source": source,
        "filename": filename,
        "file_type": file_type,
        "document_id": document_id,
        "source_location": "page:1",
        **(metadata or {}),
    }
    return RetrievedChunk(
        chunk=Chunk(
            id=chunk_id,
            document_id=document_id,
            text=text,
            chunk_index=0,
            metadata=chunk_metadata,
            token_count=len(text.split()),
        ),
        score=score,
    )
