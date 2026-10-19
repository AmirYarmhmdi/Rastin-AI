"""File guide.

- Use: Routes message requests between direct RAG and LangGraph orchestration.
- Usage: Import RoutedQuestionAnsweringService from API dependency wiring.
- Duties: Applies deterministic route criteria and adapts LangGraph output into
  the stable question/message answer contract.
- Depends on: Project modules: agent graph, database enums, repositories,
  services.documents, and services.questions.
"""

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from rastin_ai.database.enums import DocumentStatus, WorkflowExecutionStatus
from rastin_ai.observability import (
    observed_span,
    observed_workflow,
    safe_update_observation,
    trace_id_from_observation,
)
from rastin_ai.repositories.workflow_execution import (
    WorkflowExecutionRecord,
    WorkflowExecutionRepository,
)
from rastin_ai.services.documents import DocumentService
from rastin_ai.services.questions import (
    QUESTION_STATUS_INDEXING_FAILED,
    QUESTION_STATUS_NOT_READY,
    QuestionAnswer,
    QuestionAnsweringService,
    QuestionInput,
)

LANGGRAPH_WORKFLOW_NAME = "langgraph_orchestration"
ORCHESTRATION_STATUS_FAILED = "failed"


class OrchestrationRoute(StrEnum):
    DIRECT_RAG = "direct_rag"
    LANGGRAPH = "langgraph"


@dataclass(frozen=True)
class OrchestrationDecision:
    route: OrchestrationRoute
    reason: str
    matched_rules: tuple[str, ...] = ()


class OrchestrationRouter(Protocol):
    def decide(self, question_input: QuestionInput) -> OrchestrationDecision:
        """Choose the execution path for one message request."""


class AgentGraphInvoker(Protocol):
    def invoke(
        self,
        input: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke a LangGraph-compatible graph and return final state."""


class RuleBasedOrchestrationRouter:
    """Deterministic, explainable route selector for message orchestration."""

    _LANGGRAPH_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "comparison",
            (
                "compare",
                "contrast",
                "against",
                "versus",
                " vs ",
                "differences",
                "similarities",
                "gaps",
                "gap analysis",
            ),
        ),
        (
            "cross_document_synthesis",
            (
                "contradiction",
                "contradictions",
                "duplicate",
                "duplicates",
                "deduplicate",
                "combine",
                "synthesize",
                "across documents",
                "multiple documents",
            ),
        ),
        (
            "structured_output",
            (
                "create a table",
                "make a table",
                "produce a table",
                "create a report",
                "generate a report",
                "write a report",
                "matrix",
                "extract requirements",
                "requirements table",
                "structured result",
            ),
        ),
        (
            "structured_data_tooling",
            (
                "csv",
                "xlsx",
                "spreadsheet",
                "workbook",
                "worksheet",
                "calculate",
                "statistics",
                "aggregate",
                "group by",
                "sort",
                "filter",
                "analyze data",
                "inspect data",
            ),
        ),
        (
            "clarification_or_scope",
            (
                "clarifying question",
                "ask me",
                "if insufficient",
                "if the evidence is insufficient",
            ),
        ),
    )

    def decide(self, question_input: QuestionInput) -> OrchestrationDecision:
        question = _normalize_text(question_input.question)
        matched_rules = [
            rule_name
            for rule_name, phrases in self._LANGGRAPH_RULES
            if rule_name != "structured_data_tooling"
            if any(phrase in question for phrase in phrases)
        ]
        if _has_structured_data_signal(question):
            matched_rules.append("structured_data_tooling")
        matched_rules = tuple(dict.fromkeys(matched_rules))
        if matched_rules:
            return OrchestrationDecision(
                route=OrchestrationRoute.LANGGRAPH,
                reason="Request explicitly requires multi-step or tool orchestration.",
                matched_rules=matched_rules,
            )

        return OrchestrationDecision(
            route=OrchestrationRoute.DIRECT_RAG,
            reason="Default simple evidence-grounded document QA path.",
        )


class RoutedQuestionAnsweringService:
    """QuestionAnsweringService facade that chooses direct RAG or LangGraph."""

    def __init__(
        self,
        *,
        direct_question_service: QuestionAnsweringService,
        workflow_repository: WorkflowExecutionRepository,
        document_service: DocumentService,
        agent_graph: AgentGraphInvoker,
        user_id: UUID,
        router: OrchestrationRouter | None = None,
    ) -> None:
        self._direct_question_service = direct_question_service
        self._workflow_repository = workflow_repository
        self._document_service = document_service
        self._agent_graph = agent_graph
        self._user_id = user_id
        self._router = router or RuleBasedOrchestrationRouter()

    async def answer(self, question_input: QuestionInput) -> QuestionAnswer:
        with observed_span(
            name="orchestration.route_decision",
            input={
                "question_chars": len(question_input.question),
                "document_count": len(question_input.document_ids),
                "attachment_count": len(question_input.attachments),
                "history_turn_count": len(question_input.conversation_history),
            },
            metadata={
                "session_id": (
                    str(question_input.session_id)
                    if question_input.session_id is not None
                    else None
                )
            },
        ) as observation:
            decision = self._router.decide(question_input)
            safe_update_observation(
                observation,
                output={
                    "route": decision.route.value,
                    "reason": decision.reason,
                    "matched_rules": list(decision.matched_rules),
                },
            )
        if decision.route is OrchestrationRoute.DIRECT_RAG:
            return await self._direct_question_service.answer(
                _with_route_metadata(question_input, decision)
            )
        if question_input.project_retrieval_scope is not None:
            scoped_direct_decision = OrchestrationDecision(
                route=OrchestrationRoute.DIRECT_RAG,
                reason=(
                    "Project chat requests use scoped direct retrieval until "
                    "project-scoped LangGraph retrieval tools are available."
                ),
            )
            return await self._direct_question_service.answer(
                _with_route_metadata(question_input, scoped_direct_decision)
            )

        return await self._answer_with_langgraph(question_input, decision)

    async def _answer_with_langgraph(
        self,
        question_input: QuestionInput,
        decision: OrchestrationDecision,
    ) -> QuestionAnswer:
        with observed_span(
            name="workflow.persist.start",
            input={"workflow_name": LANGGRAPH_WORKFLOW_NAME},
            metadata={"route": decision.route.value},
        ) as observation:
            workflow_scope: dict[str, Any] = {}
            if question_input.project_retrieval_scope is not None:
                workflow_scope["organization_id"] = (
                    question_input.project_retrieval_scope.organization_id
                )
                workflow_scope["project_id"] = (
                    question_input.project_retrieval_scope.project_id
                )
            workflow = await self._workflow_repository.create(
                workflow_name=LANGGRAPH_WORKFLOW_NAME,
                status=WorkflowExecutionStatus.RUNNING,
                user_id=self._user_id,
                input_payload=_workflow_input_payload(question_input, decision),
                session_id=question_input.session_id,
                **workflow_scope,
            )
            safe_update_observation(
                observation,
                output={"workflow_id": str(workflow.id), "status": workflow.status},
            )

        with observed_workflow(
            name="message.langgraph",
            input={
                "question_chars": len(question_input.question),
                "document_count": len(question_input.document_ids),
                "attachment_count": len(question_input.attachments),
                "history_turn_count": len(question_input.conversation_history),
            },
            metadata={
                "workflow_type": LANGGRAPH_WORKFLOW_NAME,
                "workflow_id": str(workflow.id),
                "session_id": (
                    str(question_input.session_id)
                    if question_input.session_id is not None
                    else None
                ),
                "route": decision.route.value,
                "document_ids": [
                    str(document_id) for document_id in question_input.document_ids
                ],
                "attachment_document_ids": [
                    str(attachment.document_id)
                    for attachment in question_input.attachments
                ],
                "matched_rules": list(decision.matched_rules),
            },
            session_id=(
                str(question_input.session_id)
                if question_input.session_id is not None
                else None
            ),
        ) as observation:
            await self._persist_workflow_trace_id(
                workflow.id,
                trace_id_from_observation(observation),
            )
            return await self._answer_with_langgraph_workflow(
                question_input,
                decision,
                workflow,
                observation,
            )

    async def _answer_with_langgraph_workflow(
        self,
        question_input: QuestionInput,
        decision: OrchestrationDecision,
        workflow: WorkflowExecutionRecord,
        observation: Any,
    ) -> QuestionAnswer:
        with observed_span(
            name="langgraph.document_scope_validation",
            input={"document_count": len(question_input.document_ids)},
            metadata={
                "workflow_id": str(workflow.id),
                "document_ids": [
                    str(document_id) for document_id in question_input.document_ids
                ],
            },
        ) as scope_observation:
            scope_result = await self._document_scope_result(
                list(question_input.document_ids)
            )
            safe_update_observation(
                scope_observation,
                output={
                    "status": scope_result.status if scope_result is not None else "ok"
                },
            )
        if scope_result is not None:
            with observed_span(
                name="workflow.persist.complete",
                input={"workflow_id": str(workflow.id), "status": scope_result.status},
                metadata={"route": decision.route.value},
            ) as completion_observation:
                await self._workflow_repository.complete(
                    workflow.id,
                    user_id=self._user_id,
                    output_payload={
                        "route": decision.route.value,
                        "status": scope_result.status,
                        "answer": scope_result.answer,
                        "message": scope_result.message,
                        "citations": [],
                        "sources": [],
                        "workflow_details": _langgraph_workflow_details(
                            decision,
                            status=scope_result.status,
                            message=scope_result.message,
                        ),
                    },
                )
                safe_update_observation(
                    completion_observation,
                    output={"status": scope_result.status},
                )
            answer = replace(scope_result, workflow_id=workflow.id)
            safe_update_observation(
                observation,
                output={"status": answer.status, "source_count": 0},
            )
            return answer

        try:
            with observed_span(
                name="langgraph.invoke",
                input={
                    "workflow_id": str(workflow.id),
                    "document_count": len(question_input.document_ids),
                    "attachment_count": len(question_input.attachments),
                },
                metadata={"route": decision.route.value},
            ) as graph_observation:
                graph_state = self._agent_graph.invoke(
                    _graph_input(question_input, decision, workflow),
                    config={
                        "metadata": {
                            "route": decision.route.value,
                            "workflow_id": str(workflow.id),
                            "user_id": str(self._user_id),
                            "session_id": (
                                str(question_input.session_id)
                                if question_input.session_id is not None
                                else None
                            ),
                        }
                    },
                )
                safe_update_observation(
                    graph_observation,
                    output={
                        "has_error": bool(graph_state.get("error")),
                        "plan_step_count": len(graph_state.get("plan") or ()),
                    },
                )
        except Exception:
            answer = await self._fail_langgraph_workflow(
                workflow,
                decision,
                "LangGraph orchestration failed.",
            )
            safe_update_observation(
                observation,
                output={"status": answer.status, "message": answer.message},
            )
            return answer

        error = graph_state.get("error")
        response = _safe_response_text(graph_state.get("response"))
        citations = _extract_source_references(graph_state, key="citations")
        sources = _extract_source_references(graph_state, key="sources") or citations
        workflow_details = _langgraph_workflow_details(
            decision,
            status=(
                ORCHESTRATION_STATUS_FAILED
                if isinstance(error, str) and error
                else "answered"
            ),
            message=error if isinstance(error, str) else None,
            plan=tuple(graph_state.get("plan") or ()),
        )

        if isinstance(error, str) and error:
            with observed_span(
                name="workflow.persist.failed",
                input={"workflow_id": str(workflow.id), "status": "failed"},
                metadata={"route": decision.route.value},
            ) as failure_observation:
                await self._workflow_repository.fail(
                    workflow.id,
                    user_id=self._user_id,
                    error_message=_safe_error_message(error),
                )
                safe_update_observation(
                    failure_observation,
                    output={"status": ORCHESTRATION_STATUS_FAILED},
                )
            answer = QuestionAnswer(
                answer=response or "Unable to complete request with orchestration.",
                workflow_id=workflow.id,
                session_id=workflow.session_id,
                sources=sources,
                workflow_details=workflow_details,
                status=ORCHESTRATION_STATUS_FAILED,
                message=_safe_error_message(error),
                citations=citations,
            )
            safe_update_observation(
                observation,
                output={
                    "status": answer.status,
                    "source_count": len(answer.sources),
                    "citation_count": len(answer.citations),
                },
            )
            return answer

        with observed_span(
            name="workflow.persist.complete",
            input={"workflow_id": str(workflow.id), "status": "answered"},
            metadata={"route": decision.route.value},
        ) as completion_observation:
            await self._workflow_repository.complete(
                workflow.id,
                user_id=self._user_id,
                output_payload={
                    "route": decision.route.value,
                    "status": "answered",
                    "answer": response,
                    "sources": list(sources),
                    "citations": list(citations),
                    "workflow_details": list(workflow_details),
                    "matched_rules": list(decision.matched_rules),
                },
            )
            safe_update_observation(
                completion_observation,
                output={"status": "answered"},
            )
        answer = QuestionAnswer(
            answer=response,
            workflow_id=workflow.id,
            session_id=workflow.session_id,
            sources=sources,
            workflow_details=workflow_details,
            status="answered",
            citations=citations,
        )
        safe_update_observation(
            observation,
            output={
                "status": answer.status,
                "source_count": len(answer.sources),
                "citation_count": len(answer.citations),
            },
        )
        return answer

    async def _fail_langgraph_workflow(
        self,
        workflow: WorkflowExecutionRecord,
        decision: OrchestrationDecision,
        message: str,
    ) -> QuestionAnswer:
        with observed_span(
            name="workflow.persist.failed",
            input={"workflow_id": str(workflow.id), "status": "failed"},
            metadata={"route": decision.route.value},
        ) as observation:
            await self._workflow_repository.fail(
                workflow.id,
                user_id=self._user_id,
                error_message=message,
            )
            safe_update_observation(
                observation,
                output={"status": ORCHESTRATION_STATUS_FAILED},
            )
        return QuestionAnswer(
            answer="Unable to complete request with orchestration.",
            workflow_id=workflow.id,
            session_id=workflow.session_id,
            sources=(),
            workflow_details=_langgraph_workflow_details(
                decision,
                status=ORCHESTRATION_STATUS_FAILED,
                message=message,
            ),
            status=ORCHESTRATION_STATUS_FAILED,
            message=message,
            citations=(),
        )

    async def _document_scope_result(
        self,
        document_ids: list[UUID],
    ) -> QuestionAnswer | None:
        if not document_ids:
            return None

        records = await self._document_service.get_documents(document_ids)
        failed_records = [
            record for record in records if record.status == DocumentStatus.FAILED.value
        ]
        if failed_records:
            message = "; ".join(
                f"{record.filename}: "
                f"{record.indexing_error_code or 'INDEXING_FAILED'}"
                for record in failed_records
            )
            return QuestionAnswer(
                answer=(
                    "One or more selected documents failed indexing and cannot be "
                    "used for orchestration."
                ),
                workflow_id=None,
                sources=(),
                workflow_details=(),
                status=QUESTION_STATUS_INDEXING_FAILED,
                message=message,
                citations=(),
            )

        not_ready_records = [
            record
            for record in records
            if record.status
            in {
                DocumentStatus.UPLOADED.value,
                DocumentStatus.PROCESSING.value,
            }
        ]
        if not_ready_records:
            filenames = ", ".join(record.filename for record in not_ready_records)
            return QuestionAnswer(
                answer=(
                    "One or more selected documents are not ready for orchestration "
                    "yet."
                ),
                workflow_id=None,
                sources=(),
                workflow_details=(),
                status=QUESTION_STATUS_NOT_READY,
                message=f"Document indexing is still pending for: {filenames}",
                citations=(),
            )

        return None

    async def _persist_workflow_trace_id(
        self,
        workflow_id: UUID,
        trace_id: str | None,
    ) -> None:
        if trace_id is None:
            return
        try:
            await self._workflow_repository.set_trace_id(
                workflow_id,
                user_id=self._user_id,
                trace_id=trace_id,
            )
        except Exception:
            return


def _with_route_metadata(
    question_input: QuestionInput,
    decision: OrchestrationDecision,
) -> QuestionInput:
    return replace(
        question_input,
        route=decision.route.value,
        route_reason=decision.reason,
        route_rules=decision.matched_rules,
    )


def _workflow_input_payload(
    question_input: QuestionInput,
    decision: OrchestrationDecision,
) -> dict[str, Any]:
    return {
        "question": question_input.question,
        "route": decision.route.value,
        "route_reason": decision.reason,
        "matched_rules": list(decision.matched_rules),
        "session_id": (
            str(question_input.session_id)
            if question_input.session_id is not None
            else None
        ),
        "document_ids": [
            str(document_id) for document_id in question_input.document_ids
        ],
        "attachment_document_ids": [
            str(attachment.document_id) for attachment in question_input.attachments
        ],
        "history_turn_count": len(question_input.conversation_history),
    }


def _graph_input(
    question_input: QuestionInput,
    decision: OrchestrationDecision,
    workflow: WorkflowExecutionRecord,
) -> dict[str, Any]:
    return {
        "user_query": _graph_user_query(question_input, decision, workflow),
    }


def _graph_user_query(
    question_input: QuestionInput,
    decision: OrchestrationDecision,
    workflow: WorkflowExecutionRecord,
) -> str:
    lines = [
        "Rastin-AI orchestration request.",
        f"Route: {decision.route.value}",
        f"Workflow ID: {workflow.id}",
    ]
    if question_input.session_id is not None:
        lines.append(f"Session ID: {question_input.session_id}")
    if question_input.document_ids:
        lines.append(
            "Selected logical document IDs: "
            + ", ".join(str(document_id) for document_id in question_input.document_ids)
        )
    if question_input.attachments:
        lines.append(
            "Attached logical document IDs: "
            + ", ".join(
                str(attachment.document_id) for attachment in question_input.attachments
            )
        )
    if question_input.conversation_history:
        lines.append("Recent conversation:")
        for item in question_input.conversation_history:
            lines.append(f"{item.role}: {item.content}")

    lines.extend(
        (
            "",
            "Use only the explicit logical document IDs and attached evidence listed "
            "above. Do not infer access to any other document.",
            f"User request: {question_input.question}",
        )
    )
    return "\n".join(lines)


def _langgraph_workflow_details(
    decision: OrchestrationDecision,
    *,
    status: str,
    message: str | None = None,
    plan: tuple[str, ...] = (),
) -> tuple[dict[str, str | None], ...]:
    details = [
        {
            "label": "Select orchestration route",
            "status": "completed",
            "summary": (
                f"{decision.route.value}: {decision.reason} "
                f"Rules: {', '.join(decision.matched_rules) or 'default'}."
            ),
        },
        {
            "label": "Invoke LangGraph",
            "status": (
                "failed" if status == ORCHESTRATION_STATUS_FAILED else "completed"
            ),
            "summary": message or f"{len(plan)} planned task(s) considered.",
        },
    ]
    return tuple(details)


def _safe_response_text(response: object) -> str:
    if isinstance(response, str) and response.strip():
        return response.strip()
    return "Unable to complete request with orchestration."


def _safe_error_message(error: str) -> str:
    return error.strip()[:512] or "LangGraph orchestration failed."


def _extract_source_references(
    graph_state: dict[str, Any],
    *,
    key: str,
) -> tuple[dict[str, Any], ...]:
    found: list[dict[str, Any]] = []
    _collect_references(graph_state.get(key), found)
    execution_result = graph_state.get("execution_result")
    successful_results = getattr(execution_result, "successful_results", None)
    if isinstance(successful_results, dict):
        _collect_references(successful_results, found)

    return tuple(_dedupe_references(found))


def _collect_references(value: object, found: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        for key in ("citations", "sources"):
            nested = value.get(key)
            if isinstance(nested, list | tuple):
                _collect_references(nested, found)
        if _is_safe_source_reference(value):
            found.append(dict(value))
        else:
            for item in value.values():
                _collect_references(item, found)
    elif isinstance(value, list | tuple):
        for item in value:
            _collect_references(item, found)


def _is_safe_source_reference(value: dict[str, Any]) -> bool:
    return "document_id" in value and not any(
        forbidden_key in value
        for forbidden_key in ("storage_key", "path", "local_path", "text")
    )


def _dedupe_references(references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []
    for reference in references:
        key = tuple(
            sorted((str(name), str(value)) for name, value in reference.items())
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(reference)
    return deduped


def _normalize_text(value: str) -> str:
    return f" {' '.join(value.lower().split())} "


def _has_structured_data_signal(question: str) -> bool:
    data_terms = (
        " csv ",
        " xlsx ",
        " spreadsheet ",
        " workbook ",
        " worksheet ",
    )
    action_terms = (
        " inspect ",
        " analyze ",
        " analyse ",
        " calculate ",
        " statistics ",
        " aggregate ",
        " group by ",
        " sort ",
        " filter ",
        " produce a table ",
        " create a table ",
        " make a table ",
    )
    return any(term in question for term in data_terms) and any(
        term in question for term in action_terms
    )
