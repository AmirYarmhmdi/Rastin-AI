"""File guide.

- Use: Contains unit tests for message orchestration routing.
- Usage: Run with pytest when checking direct RAG versus LangGraph selection.
- Duties: Uses fakes to verify deterministic routing, context propagation, and
  workflow persistence.
- Depends on: Project modules: API dependencies, repositories, and services.
"""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import rastin_ai.observability.langfuse as langfuse_observability
from rastin_ai.api.dependencies import ensure_core_document_capabilities_registered
from rastin_ai.database.enums import WorkflowExecutionStatus
from rastin_ai.repositories.workflow_execution import WorkflowExecutionRecord
from rastin_ai.services.conversations import ConversationHistoryItem
from rastin_ai.services.documents import DocumentRecord, DocumentUpload
from rastin_ai.services.orchestration import (
    OrchestrationRoute,
    RoutedQuestionAnsweringService,
    RuleBasedOrchestrationRouter,
)
from rastin_ai.services.questions import QuestionAnswer, QuestionInput
from rastin_ai.tools.registry import get_tool, get_tool_definitions

DOCUMENT_ID = UUID("11111111-1111-4111-8111-111111111111")
SECOND_DOCUMENT_ID = UUID("22222222-2222-4222-8222-222222222222")
SESSION_ID = UUID("33333333-3333-4333-8333-333333333333")
WORKFLOW_ID = UUID("44444444-4444-4444-8444-444444444444")
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class FakeDirectQuestionService:
    def __init__(self) -> None:
        self.requests: list[QuestionInput] = []

    async def answer(self, question_input: QuestionInput) -> QuestionAnswer:
        self.requests.append(question_input)
        return QuestionAnswer(
            answer="Direct answer.",
            workflow_id=WORKFLOW_ID,
            session_id=question_input.session_id,
            sources=({"document_id": str(DOCUMENT_ID)},),
            citations=({"document_id": str(DOCUMENT_ID)},),
        )


class FakeDocumentService:
    def __init__(self) -> None:
        self.requests: list[list[UUID]] = []

    async def upload_document(self, upload: DocumentUpload) -> DocumentRecord:
        raise AssertionError("Upload is not part of orchestration tests.")

    async def list_documents(self) -> list[DocumentRecord]:
        return []

    async def ensure_documents_exist(self, document_ids: list[UUID]) -> None:
        await self.get_documents(document_ids)

    async def get_documents(self, document_ids: list[UUID]) -> list[DocumentRecord]:
        self.requests.append(document_ids)
        return [
            DocumentRecord(
                document_id=document_id,
                filename=f"{document_id}.txt",
                content_type="text/plain",
                status="indexed",
                created_at=NOW,
                size_bytes=10,
            )
            for document_id in document_ids
        ]


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
    ) -> WorkflowExecutionRecord:
        assert user_id == USER_ID
        record = WorkflowExecutionRecord(
            user_id=user_id,
            id=uuid4(),
            session_id=session_id or SESSION_ID,
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


class FakeAgentGraph:
    def __init__(self, result: dict | None = None) -> None:
        self.result = result or {
            "response": "LangGraph answer.",
            "plan": ["task_1: document.read.csv"],
            "citations": ({"document_id": str(DOCUMENT_ID), "chunk_id": "chunk-1"},),
        }
        self.calls: list[tuple[dict, dict | None]] = []

    def invoke(self, input: dict, config: dict | None = None) -> dict:
        self.calls.append((input, config))
        return self.result


def _service(
    *,
    graph: FakeAgentGraph | None = None,
) -> tuple[
    RoutedQuestionAnsweringService,
    FakeDirectQuestionService,
    FakeWorkflowRepository,
    FakeDocumentService,
    FakeAgentGraph,
]:
    direct_service = FakeDirectQuestionService()
    workflow_repository = FakeWorkflowRepository()
    document_service = FakeDocumentService()
    graph = graph or FakeAgentGraph()
    return (
        RoutedQuestionAnsweringService(
            direct_question_service=direct_service,
            workflow_repository=workflow_repository,
            document_service=document_service,
            agent_graph=graph,
            user_id=USER_ID,
        ),
        direct_service,
        workflow_repository,
        document_service,
        graph,
    )


def test_simple_document_qa_routes_to_direct_rag_without_langgraph() -> None:
    asyncio.run(_run_simple_direct_test())


async def _run_simple_direct_test() -> None:
    service, direct_service, workflow_repository, document_service, graph = _service()

    answer = await service.answer(
        QuestionInput(
            question="What does this document say about revenue?",
            document_ids=[DOCUMENT_ID],
            session_id=SESSION_ID,
        )
    )

    assert answer.answer == "Direct answer."
    assert direct_service.requests[0].route == OrchestrationRoute.DIRECT_RAG.value
    assert direct_service.requests[0].document_ids == [DOCUMENT_ID]
    assert direct_service.requests[0].session_id == SESSION_ID
    assert graph.calls == []
    assert workflow_repository.created == []
    assert document_service.requests == []


def test_comparison_request_routes_to_langgraph() -> None:
    asyncio.run(_run_comparison_langgraph_test())


async def _run_comparison_langgraph_test() -> None:
    service, direct_service, workflow_repository, document_service, graph = _service()

    answer = await service.answer(
        QuestionInput(
            question="Compare this CV against the job description and identify gaps.",
            document_ids=[DOCUMENT_ID, SECOND_DOCUMENT_ID],
            session_id=SESSION_ID,
            conversation_history=(
                ConversationHistoryItem(role="user", content="Previous question"),
            ),
        )
    )

    assert answer.answer == "LangGraph answer."
    assert answer.workflow_id == workflow_repository.created[0].id
    assert answer.citations == (
        {"document_id": str(DOCUMENT_ID), "chunk_id": "chunk-1"},
    )
    assert direct_service.requests == []
    assert document_service.requests == [[DOCUMENT_ID, SECOND_DOCUMENT_ID]]
    assert workflow_repository.created[0].input_payload["route"] == "langgraph"
    assert workflow_repository.completed[0][1]["route"] == "langgraph"
    graph_input, config = graph.calls[0]
    assert str(SESSION_ID) in graph_input["user_query"]
    assert str(DOCUMENT_ID) in graph_input["user_query"]
    assert str(SECOND_DOCUMENT_ID) in graph_input["user_query"]
    assert "Previous question" in graph_input["user_query"]
    assert config["metadata"]["route"] == "langgraph"
    assert config["metadata"]["user_id"] == str(USER_ID)


def test_structured_data_request_routes_to_langgraph() -> None:
    decision = RuleBasedOrchestrationRouter().decide(
        QuestionInput(
            question="Inspect this CSV data, calculate totals, and produce a table.",
            document_ids=[DOCUMENT_ID],
        )
    )

    assert decision.route is OrchestrationRoute.LANGGRAPH
    assert "structured_data_tooling" in decision.matched_rules
    assert "structured_output" in decision.matched_rules


def test_route_criteria_are_deterministic_and_default_to_direct_rag() -> None:
    router = RuleBasedOrchestrationRouter()

    decisions = [
        router.decide(
            QuestionInput(question="Summarize this CV.", document_ids=[DOCUMENT_ID])
        )
        for _ in range(3)
    ]
    report_summary = router.decide(
        QuestionInput(question="Summarize this report.", document_ids=[DOCUMENT_ID])
    )

    assert {decision.route for decision in decisions} == {OrchestrationRoute.DIRECT_RAG}
    assert all(decision.matched_rules == () for decision in decisions)
    assert report_summary.route is OrchestrationRoute.DIRECT_RAG


def test_core_document_capabilities_are_registered_for_graph_use() -> None:
    ensure_core_document_capabilities_registered()
    ensure_core_document_capabilities_registered()

    capability_names = {definition.name for definition in get_tool_definitions()}

    assert {
        "document.read.pdf",
        "document.read.csv",
        "document.read.excel.workbook",
        "document.read.excel.sheet",
        "document.read.text",
        "document.read.json",
        "document.read.docx",
    }.issubset(capability_names)
    assert get_tool("document.read.csv") is not None


def test_langgraph_failure_is_persisted_and_returned_safely() -> None:
    asyncio.run(_run_failure_test())


async def _run_failure_test() -> None:
    service, _, workflow_repository, _, _ = _service(
        graph=FakeAgentGraph(
            {
                "error": "Planner failed unexpectedly.",
                "response": "Unable to complete request: Planner failed unexpectedly.",
            }
        )
    )

    answer = await service.answer(
        QuestionInput(
            question="Compare the documents and find contradictions.",
            document_ids=[DOCUMENT_ID],
            session_id=SESSION_ID,
        )
    )

    assert answer.status == "failed"
    assert answer.message == "Planner failed unexpectedly."
    assert workflow_repository.failed == [
        (workflow_repository.created[0].id, "Planner failed unexpectedly.")
    ]
    assert workflow_repository.completed == []


def test_langgraph_validates_only_explicit_document_scope() -> None:
    asyncio.run(_run_document_scope_test())


def test_langgraph_route_persists_observability_trace_id(monkeypatch) -> None:
    from test_observability import FakeLangfuseClient

    fake_client = FakeLangfuseClient()
    monkeypatch.setattr(
        langfuse_observability,
        "_get_langfuse_client",
        lambda settings=None: fake_client,
    )

    asyncio.run(_run_langgraph_trace_persistence_test(fake_client))


async def _run_document_scope_test() -> None:
    service, _, _, document_service, _ = _service()

    await service.answer(
        QuestionInput(
            question="Compare the selected documents.",
            document_ids=[SECOND_DOCUMENT_ID],
            session_id=SESSION_ID,
        )
    )

    assert document_service.requests == [[SECOND_DOCUMENT_ID]]


async def _run_langgraph_trace_persistence_test(fake_client) -> None:
    service, _, workflow_repository, _, _ = _service()

    await service.answer(
        QuestionInput(
            question="Compare the selected documents.",
            document_ids=[DOCUMENT_ID],
            session_id=SESSION_ID,
        )
    )

    assert workflow_repository.trace_updates == [
        (workflow_repository.created[0].id, "trace-test")
    ]
    names = [
        observation.start_kwargs["name"] for observation in fake_client.observations
    ]
    assert "orchestration.route_decision" in names
    assert "message.langgraph" in names
    assert "langgraph.invoke" in names
