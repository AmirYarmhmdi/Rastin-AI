"""File guide.

- Use: Coordinates question answering through retrieval, context, and response
  generation services.
- Usage: Import QuestionAnsweringService and RAGQuestionAnsweringService from
  rastin_ai.services.questions.
- Duties: Validates document scope, runs RAG retrieval, records workflow state,
  and delegates final answer generation.
- Depends on: Project modules: rastin_ai.agent, rastin_ai.core.exceptions,
  rastin_ai.database.enums, rastin_ai.rag, rastin_ai.repositories, and
  rastin_ai.services.documents.
"""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Protocol
from uuid import UUID

from fastapi import status

from rastin_ai.agent.exceptions import AgentError
from rastin_ai.agent.response_generator import ResponseGenerator
from rastin_ai.core.exceptions import AppException
from rastin_ai.database.enums import (
    DocumentScope,
    DocumentStatus,
    WorkflowExecutionStatus,
)
from rastin_ai.observability import (
    observed_span,
    observed_workflow,
    safe_update_observation,
    trace_id_from_observation,
)
from rastin_ai.rag.chunking.recursive import RecursiveTextChunker
from rastin_ai.rag.context.builder import ContextBuilder
from rastin_ai.rag.exceptions import RAGError
from rastin_ai.rag.models import BuiltContext, Document, RetrievedChunk
from rastin_ai.rag.retrieval.retriever import Retriever
from rastin_ai.repositories.workflow_execution import (
    WorkflowExecutionRecord,
    WorkflowExecutionRepository,
)
from rastin_ai.services.conversations import ConversationHistoryItem
from rastin_ai.services.documents import DocumentRecord, DocumentService

QUESTION_WORKFLOW_NAME = "question_answering"
QUESTION_STATUS_ANSWERED = "answered"
QUESTION_STATUS_NO_EVIDENCE = "no_evidence"
QUESTION_STATUS_NOT_READY = "not_ready"
QUESTION_STATUS_INDEXING_FAILED = "indexing_failed"
QUESTION_STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class QuestionAnsweringError(AppException):
    """Raised when the question-answering workflow fails safely."""

    def __init__(self, message: str = "Question answering failed.") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            error_code="QUESTION_ANSWERING_FAILED",
        )


class QuestionAnsweringUnavailableError(AppException):
    """Raised when required question-answering runtime services are unavailable."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="QUESTION_ANSWERING_UNAVAILABLE",
        )


@dataclass(frozen=True)
class QuestionAttachment:
    document_id: UUID
    filename: str
    content_type: str | None
    size_bytes: int
    status: str
    text: str | None = None
    documents: tuple[Document, ...] = ()
    extraction_error_code: str | None = None
    extraction_error_message: str | None = None


@dataclass(frozen=True)
class ProjectRetrievalScope:
    organization_id: UUID
    project_id: UUID
    session_id: UUID


@dataclass(frozen=True)
class QuestionInput:
    question: str
    document_ids: list[UUID]
    attachments: tuple[QuestionAttachment, ...] = ()
    session_id: UUID | None = None
    conversation_history: tuple[ConversationHistoryItem, ...] = ()
    route: str | None = None
    route_reason: str | None = None
    route_rules: tuple[str, ...] = ()
    project_retrieval_scope: ProjectRetrievalScope | None = None


@dataclass(frozen=True)
class QuestionAnswer:
    answer: str
    workflow_id: UUID | None
    sources: tuple[dict[str, Any], ...]
    session_id: UUID | None = None
    workflow_details: tuple[dict[str, str | None], ...] = ()
    status: str = QUESTION_STATUS_ANSWERED
    message: str | None = None
    citations: tuple[dict[str, Any], ...] = ()
    retrieved_contexts: tuple[str, ...] = ()
    model_name: str | None = None
    token_usage: dict[str, int] | None = None


class QuestionAnsweringService(Protocol):
    async def answer(self, question_input: QuestionInput) -> QuestionAnswer:
        """Answer a user question using the configured orchestration path."""


class RAGQuestionAnsweringService:
    """Question-answering facade over deterministic RAG and LLM response output."""

    def __init__(
        self,
        *,
        retriever: Retriever,
        context_builder: ContextBuilder,
        response_generator: ResponseGenerator,
        document_service: DocumentService,
        workflow_repository: WorkflowExecutionRepository | None = None,
        user_id: UUID,
        top_k: int = 5,
    ) -> None:
        self._retriever = retriever
        self._context_builder = context_builder
        self._response_generator = response_generator
        self._document_service = document_service
        self._workflow_repository = workflow_repository
        self._user_id = user_id
        self._top_k = top_k
        self._attachment_chunker = RecursiveTextChunker()

    async def answer(self, question_input: QuestionInput) -> QuestionAnswer:
        question = question_input.question.strip()
        scoped_question = _question_with_history(
            question,
            question_input.conversation_history,
        )
        workflow = await self._start_workflow(
            question,
            question_input.document_ids,
            session_id=question_input.session_id,
            route=question_input.route,
            route_reason=question_input.route_reason,
            route_rules=question_input.route_rules,
            project_retrieval_scope=question_input.project_retrieval_scope,
        )

        with observed_workflow(
            name="message.direct_rag",
            input=_observed_question_input(question_input),
            metadata=_observed_question_metadata(question_input, workflow),
            session_id=(
                str(question_input.session_id)
                if question_input.session_id is not None
                else None
            ),
        ) as observation:
            await self._persist_workflow_trace_id(
                _workflow_id(workflow),
                trace_id_from_observation(observation),
            )
            answer = await self._answer_with_workflow(
                question_input,
                workflow,
                scoped_question,
            )
            safe_update_observation(
                observation,
                output={
                    "workflow_id": (
                        str(answer.workflow_id)
                        if answer.workflow_id is not None
                        else None
                    ),
                    "status": answer.status,
                    "source_count": len(answer.sources),
                    "citation_count": len(answer.citations),
                },
            )
            return answer

    async def _answer_with_workflow(
        self,
        question_input: QuestionInput,
        workflow: WorkflowExecutionRecord | None,
        scoped_question: str,
    ) -> QuestionAnswer:
        try:
            if question_input.project_retrieval_scope is not None:
                context = self._retrieve_project_context(
                    scoped_question,
                    question_input.project_retrieval_scope,
                )
                citations = _citations_from_sources(context.sources)
                if not citations:
                    return await self._complete_without_generation(
                        workflow,
                        status=QUESTION_STATUS_NO_EVIDENCE,
                        answer=(
                            "No relevant evidence was found in the project library "
                            "or this chat's attachments."
                        ),
                        message=(
                            "Project-scoped retrieval returned no relevant chunks."
                        ),
                    )
                if _context_is_insufficient(scoped_question, context.text):
                    return await self._complete_without_generation(
                        workflow,
                        status=QUESTION_STATUS_INSUFFICIENT_EVIDENCE,
                        answer=(
                            "The project returned evidence, but it is insufficient "
                            "to answer the question reliably."
                        ),
                        message=(
                            "Retrieved project evidence did not contain enough "
                            "lexical support for the question."
                        ),
                        citations=citations,
                    )
            elif question_input.attachments:
                context = self._retrieve_attachment_context(
                    scoped_question,
                    question_input.attachments,
                )
                if context is None:
                    return await self._complete_without_generation(
                        workflow,
                        status=QUESTION_STATUS_NO_EVIDENCE,
                        answer="No extractable attachment evidence was available.",
                        message="No extractable attachment evidence was available.",
                        attachments=question_input.attachments,
                    )
            else:
                scope_result = await self._document_scope_result(
                    question_input.document_ids
                )
                if scope_result is not None:
                    return await self._complete_without_generation(
                        workflow,
                        status=scope_result["status"],
                        answer=scope_result["answer"],
                        message=scope_result["message"],
                        document_ids=question_input.document_ids,
                    )

                context = self._retrieve_context(
                    scoped_question,
                    question_input.document_ids,
                    (),
                )
                citations = _citations_from_sources(context.sources)
                if not citations:
                    return await self._complete_without_generation(
                        workflow,
                        status=QUESTION_STATUS_NO_EVIDENCE,
                        answer=(
                            "No relevant evidence was found in the selected indexed "
                            "documents."
                        ),
                        message=(
                            "The selected indexed documents returned no relevant "
                            "retrieval chunks."
                        ),
                        document_ids=question_input.document_ids,
                    )
                if _context_is_insufficient(scoped_question, context.text):
                    return await self._complete_without_generation(
                        workflow,
                        status=QUESTION_STATUS_INSUFFICIENT_EVIDENCE,
                        answer=(
                            "The selected documents returned evidence, but it is "
                            "insufficient to answer the question reliably."
                        ),
                        message=(
                            "Retrieved evidence did not contain enough lexical "
                            "support for the question."
                        ),
                        document_ids=question_input.document_ids,
                        citations=citations,
                    )

            citations = _citations_from_sources(context.sources)
            answer = self._response_generator.generate_response(
                user_query=scoped_question,
                plan=[
                    "retrieve relevant indexed document context",
                    "generate a grounded answer from retrieved context",
                ],
                tool_name="rag.retrieve",
                tool_result={
                    "text": context.text,
                    "citations": list(citations),
                    "sources": list(citations),
                    "status": QUESTION_STATUS_ANSWERED,
                },
            )
            generation_metadata = _generation_metadata(self._response_generator)
        except AppException as exc:
            await self._mark_workflow_failed(_workflow_id(workflow), exc.message)
            raise
        except (AgentError, RAGError) as exc:
            await self._mark_workflow_failed(
                _workflow_id(workflow),
                "Question answering workflow failed.",
            )
            raise QuestionAnsweringError() from exc
        except Exception as exc:
            await self._mark_workflow_failed(
                _workflow_id(workflow),
                "Question answering workflow failed.",
            )
            raise QuestionAnsweringError() from exc

        sources = context.sources
        attachments = _attachment_payload(question_input.attachments)
        workflow_details = _workflow_details(
            attachment_count=len(attachments),
            attachment_context_count=_attachment_context_count(
                question_input.attachments,
            ),
            source_count=len(sources),
        )
        await self._mark_workflow_completed(
            _workflow_id(workflow),
            {
                "status": QUESTION_STATUS_ANSWERED,
                "answer": answer,
                "sources": list(citations),
                "citations": list(citations),
                "attachments": attachments,
                "artifacts": [],
                "workflow_details": workflow_details,
            },
        )
        return QuestionAnswer(
            answer=answer,
            workflow_id=_workflow_id(workflow),
            session_id=workflow.session_id if workflow is not None else None,
            sources=citations,
            workflow_details=tuple(workflow_details),
            status=QUESTION_STATUS_ANSWERED,
            citations=citations,
            retrieved_contexts=(context.text,) if context.text else (),
            model_name=generation_metadata.get("model_name"),
            token_usage=generation_metadata.get("token_usage"),
        )

    def _retrieve_context(
        self,
        question: str,
        document_ids: list[UUID],
        attachments: tuple[QuestionAttachment, ...] = (),
    ) -> BuiltContext:
        attachment_context = self._retrieve_attachment_context(question, attachments)
        if attachment_context is not None:
            return attachment_context

        retrieved = self._retrieve_chunks(question, document_ids)
        return self._context_builder.build(retrieved)

    def _retrieve_project_context(
        self,
        question: str,
        scope: ProjectRetrievalScope,
    ) -> BuiltContext:
        with observed_span(
            name="rag.project_scoped_retrieval",
            input={"top_k": self._top_k},
            metadata={
                "organization_id": str(scope.organization_id),
                "project_id": str(scope.project_id),
                "session_id": str(scope.session_id),
            },
        ) as observation:
            retrieved = []
            retrieved.extend(
                self._retriever.retrieve(
                    question,
                    top_k=self._top_k,
                    filters={
                        "organization_id": str(scope.organization_id),
                        "project_id": str(scope.project_id),
                        "document_scope": DocumentScope.PROJECT_LIBRARY.value,
                    },
                )
            )
            retrieved.extend(
                self._retriever.retrieve(
                    question,
                    top_k=self._top_k,
                    filters={
                        "organization_id": str(scope.organization_id),
                        "project_id": str(scope.project_id),
                        "document_scope": DocumentScope.CHAT_ATTACHMENT.value,
                        "session_id": str(scope.session_id),
                    },
                )
            )
            scoped_results = sorted(
                retrieved,
                key=lambda result: result.score,
                reverse=True,
            )[: self._top_k]
            context = self._context_builder.build(scoped_results)
            safe_update_observation(
                observation,
                output={
                    "retrieved_chunk_count": len(scoped_results),
                    "source_count": len(context.sources),
                },
            )
            return context

    def _retrieve_attachment_context(
        self,
        question: str,
        attachments: tuple[QuestionAttachment, ...],
    ) -> BuiltContext | None:
        with observed_span(
            name="message.attachment_context",
            input={"attachment_count": len(attachments), "top_k": max(self._top_k, 8)},
            metadata={
                "attachment_document_ids": [
                    str(attachment.document_id) for attachment in attachments
                ]
            },
        ) as observation:
            documents = []
            for attachment in attachments:
                if attachment.documents:
                    documents.extend(attachment.documents)
                elif attachment.text is not None and attachment.text.strip():
                    documents.append(_document_from_legacy_attachment(attachment))

            if not documents:
                safe_update_observation(
                    observation,
                    output={"status": "no_extractable_text", "document_count": 0},
                )
                return None

            chunks = self._attachment_chunker.split(documents)
            retrieved = [
                RetrievedChunk(chunk=chunk, score=_lexical_score(question, chunk.text))
                for chunk in chunks
            ]
            retrieved.sort(
                key=lambda result: (
                    result.score,
                    -result.chunk.chunk_index,
                ),
                reverse=True,
            )
            context = self._context_builder.build(retrieved[: max(self._top_k, 8)])
            safe_update_observation(
                observation,
                output={
                    "document_count": len(documents),
                    "chunk_count": len(chunks),
                    "source_count": len(context.sources),
                },
            )
            return context

    def _retrieve_chunks(
        self,
        question: str,
        document_ids: list[UUID],
    ) -> list[RetrievedChunk]:
        if not document_ids:
            return []

        with observed_span(
            name="rag.scoped_retrieval",
            input={"document_count": len(set(document_ids)), "top_k": self._top_k},
            metadata={
                "document_ids": [str(item) for item in dict.fromkeys(document_ids)],
                "user_id": str(self._user_id),
            },
        ) as observation:
            retrieved: list[RetrievedChunk] = []
            for document_id in dict.fromkeys(document_ids):
                retrieved.extend(
                    self._retriever.retrieve(
                        question,
                        top_k=self._top_k,
                        filters={
                            "document_id": str(document_id),
                            "user_id": str(self._user_id),
                        },
                    )
                )
            scoped_results = sorted(
                retrieved,
                key=lambda result: result.score,
                reverse=True,
            )[: self._top_k]
            safe_update_observation(
                observation,
                output={"retrieved_chunk_count": len(scoped_results)},
            )
            return scoped_results

    async def _document_scope_result(
        self,
        document_ids: list[UUID],
    ) -> dict[str, str] | None:
        if not document_ids:
            return {
                "status": QUESTION_STATUS_NO_EVIDENCE,
                "answer": "Select at least one indexed document to answer from.",
                "message": (
                    "Persisted-document question answering requires explicit logical "
                    "document IDs."
                ),
            }

        with observed_span(
            name="rag.document_scope_validation",
            input={"document_count": len(document_ids)},
            metadata={
                "document_ids": [str(document_id) for document_id in document_ids]
            },
        ) as observation:
            records = await self._document_service.get_documents(document_ids)
            safe_update_observation(
                observation,
                output={
                    "indexed_count": sum(
                        1
                        for record in records
                        if record.status == DocumentStatus.INDEXED.value
                    ),
                    "failed_count": sum(
                        1
                        for record in records
                        if record.status == DocumentStatus.FAILED.value
                    ),
                    "not_ready_count": sum(
                        1
                        for record in records
                        if record.status
                        in {
                            DocumentStatus.UPLOADED.value,
                            DocumentStatus.PROCESSING.value,
                        }
                    ),
                },
            )
        failed_records = [
            record for record in records if record.status == DocumentStatus.FAILED.value
        ]
        if failed_records:
            return _indexing_failed_scope_result(failed_records)

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
            return {
                "status": QUESTION_STATUS_NOT_READY,
                "answer": (
                    "One or more selected documents are not ready for question "
                    "answering yet."
                ),
                "message": f"Document indexing is still pending for: {filenames}",
            }

        non_indexed = [
            record
            for record in records
            if record.status != DocumentStatus.INDEXED.value
        ]
        if non_indexed:
            filenames = ", ".join(record.filename for record in non_indexed)
            return {
                "status": QUESTION_STATUS_NOT_READY,
                "answer": (
                    "One or more selected documents are not ready for question "
                    "answering yet."
                ),
                "message": f"Document status is not queryable for: {filenames}",
            }

        return None

    async def _complete_without_generation(
        self,
        workflow: WorkflowExecutionRecord | None,
        *,
        status: str,
        answer: str,
        message: str,
        document_ids: list[UUID] | None = None,
        attachments: tuple[QuestionAttachment, ...] = (),
        citations: tuple[dict[str, Any], ...] = (),
    ) -> QuestionAnswer:
        attachments_payload = _attachment_payload(attachments)
        workflow_details = _workflow_details(
            attachment_count=len(attachments_payload),
            attachment_context_count=_attachment_context_count(attachments),
            source_count=len(citations),
            answer_status=status,
            message=message,
        )
        await self._mark_workflow_completed(
            _workflow_id(workflow),
            {
                "status": status,
                "answer": answer,
                "message": message,
                "sources": list(citations),
                "citations": list(citations),
                "attachments": attachments_payload,
                "artifacts": [],
                "workflow_details": workflow_details,
                "document_ids": [
                    str(document_id) for document_id in (document_ids or [])
                ],
            },
        )
        return QuestionAnswer(
            answer=answer,
            workflow_id=_workflow_id(workflow),
            session_id=workflow.session_id if workflow is not None else None,
            sources=citations,
            workflow_details=tuple(workflow_details),
            status=status,
            message=message,
            citations=citations,
            retrieved_contexts=(),
        )

    async def _start_workflow(
        self,
        question: str,
        document_ids: list[UUID],
        *,
        session_id: UUID | None = None,
        route: str | None = None,
        route_reason: str | None = None,
        route_rules: tuple[str, ...] = (),
        project_retrieval_scope: ProjectRetrievalScope | None = None,
    ) -> WorkflowExecutionRecord | None:
        if self._workflow_repository is None:
            return None

        kwargs: dict[str, Any] = {}
        if project_retrieval_scope is not None:
            kwargs["organization_id"] = project_retrieval_scope.organization_id
            kwargs["project_id"] = project_retrieval_scope.project_id

        return await self._workflow_repository.create(
            workflow_name=QUESTION_WORKFLOW_NAME,
            status=WorkflowExecutionStatus.RUNNING,
            user_id=self._user_id,
            input_payload={
                "question": question,
                "document_ids": [str(document_id) for document_id in document_ids],
                "route": route,
                "route_reason": route_reason,
                "route_rules": list(route_rules),
            },
            session_id=session_id,
            **kwargs,
        )

    async def _mark_workflow_completed(
        self,
        workflow_id: UUID | None,
        output_payload: dict[str, Any],
    ) -> None:
        if workflow_id is not None and self._workflow_repository is not None:
            await self._workflow_repository.complete(
                workflow_id,
                user_id=self._user_id,
                output_payload=output_payload,
            )

    async def _mark_workflow_failed(
        self,
        workflow_id: UUID | None,
        error_message: str,
    ) -> None:
        if workflow_id is not None and self._workflow_repository is not None:
            await self._workflow_repository.fail(
                workflow_id,
                user_id=self._user_id,
                error_message=error_message,
            )

    async def _persist_workflow_trace_id(
        self,
        workflow_id: UUID | None,
        trace_id: str | None,
    ) -> None:
        if workflow_id is None or trace_id is None or self._workflow_repository is None:
            return
        try:
            await self._workflow_repository.set_trace_id(
                workflow_id,
                user_id=self._user_id,
                trace_id=trace_id,
            )
        except Exception:
            return


def _workflow_id(workflow: WorkflowExecutionRecord | None) -> UUID | None:
    return workflow.id if workflow is not None else None


def _generation_metadata(response_generator: ResponseGenerator) -> dict[str, Any]:
    metadata = getattr(response_generator, "last_generation_metadata", None)
    if metadata is None:
        return {"model_name": None, "token_usage": None}

    return {
        "model_name": getattr(metadata, "model", None),
        "token_usage": getattr(metadata, "token_usage", None),
    }


def _observed_question_input(question_input: QuestionInput) -> dict[str, Any]:
    return {
        "question_chars": len(question_input.question),
        "document_count": len(question_input.document_ids),
        "attachment_count": len(question_input.attachments),
        "history_turn_count": len(question_input.conversation_history),
        "route": question_input.route or "direct_rag",
    }


def _observed_question_metadata(
    question_input: QuestionInput,
    workflow: WorkflowExecutionRecord | None,
) -> dict[str, Any]:
    workflow_id = _workflow_id(workflow)
    return {
        "workflow_type": QUESTION_WORKFLOW_NAME,
        "workflow_id": str(workflow_id) if workflow_id is not None else None,
        "session_id": (
            str(question_input.session_id)
            if question_input.session_id is not None
            else None
        ),
        "route": question_input.route or "direct_rag",
        "document_ids": [
            str(document_id) for document_id in question_input.document_ids
        ],
        "attachment_document_ids": [
            str(attachment.document_id) for attachment in question_input.attachments
        ],
        "route_rules": list(question_input.route_rules),
        "project_retrieval_scope": (
            {
                "organization_id": str(
                    question_input.project_retrieval_scope.organization_id
                ),
                "project_id": str(question_input.project_retrieval_scope.project_id),
                "session_id": str(question_input.project_retrieval_scope.session_id),
            }
            if question_input.project_retrieval_scope is not None
            else None
        ),
    }


def _attachment_payload(
    attachments: tuple[QuestionAttachment, ...],
) -> list[dict[str, Any]]:
    return [
        {
            "document_id": str(attachment.document_id),
            "filename": attachment.filename,
            "content_type": attachment.content_type,
            "size_bytes": attachment.size_bytes,
            "status": attachment.status,
            "text_extracted": bool(
                attachment.documents or (attachment.text and attachment.text.strip())
            ),
            "extraction_error_code": attachment.extraction_error_code,
        }
        for attachment in attachments
    ]


def _workflow_details(
    *,
    attachment_count: int,
    attachment_context_count: int,
    source_count: int,
    answer_status: str = QUESTION_STATUS_ANSWERED,
    message: str | None = None,
) -> list[dict[str, str]]:
    details = []
    if attachment_count:
        if attachment_context_count:
            attachment_summary = (
                f"{attachment_count} file(s) stored. "
                f"{attachment_context_count} uploaded file(s) used as direct "
                "answer context."
            )
        else:
            attachment_summary = (
                f"{attachment_count} file(s) stored, but no extractable text was "
                "available for direct answer context."
            )
        details.append(
            {
                "label": "Store attachments",
                "status": "completed",
                "summary": attachment_summary,
            }
        )

    details.extend(
        [
            {
                "label": "Build answer context",
                "status": "completed",
                "summary": _context_summary(answer_status, source_count, message),
            },
            {
                "label": "Generate final answer",
                "status": "completed",
                "summary": _generation_summary(answer_status),
            },
        ]
    )
    return details


def _indexing_failed_scope_result(
    records: list[DocumentRecord],
) -> dict[str, str]:
    details = []
    for record in records:
        reason = record.indexing_error_code or "INDEXING_FAILED"
        details.append(f"{record.filename}: {reason}")
    return {
        "status": QUESTION_STATUS_INDEXING_FAILED,
        "answer": (
            "One or more selected documents failed indexing and cannot be used for "
            "question answering."
        ),
        "message": "; ".join(details),
    }


def _citations_from_sources(
    sources: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    return tuple(_citation_from_source(source) for source in sources)


def _citation_from_source(source: dict[str, Any]) -> dict[str, Any]:
    citation = {
        "document_id": source.get("document_id"),
        "filename": _safe_filename(source.get("filename")),
        "chunk_id": source.get("chunk_id"),
        "chunk_index": source.get("chunk_index"),
        "score": source.get("score"),
        "location_type": source.get("location_type"),
        "source_location": _safe_source_location(source.get("source_location")),
        "page_number": source.get("page_number"),
        "line_start": source.get("line_start"),
        "line_end": source.get("line_end"),
        "paragraph_index": source.get("paragraph_index"),
        "table_index": source.get("table_index"),
        "row_start": source.get("row_start"),
        "row_end": source.get("row_end"),
        "columns": source.get("columns"),
        "sheet_name": source.get("sheet_name"),
        "json_path": source.get("json_path"),
    }
    return {key: value for key, value in citation.items() if value is not None}


def _safe_filename(value: Any) -> str | None:
    if value is None:
        return None

    filename = str(value).strip()
    if not filename:
        return None

    return PureWindowsPath(PurePosixPath(filename).name).name


def _safe_source_location(value: Any) -> str | None:
    if value is None:
        return None

    location = str(value).strip()
    if not location or "/" in location or "\\" in location:
        return None

    return location


def _context_is_insufficient(question: str, context_text: str) -> bool:
    question_terms = _terms(question) - _STOP_WORDS
    if not question_terms:
        return False

    context_terms = _terms(context_text)
    return not bool(question_terms & context_terms)


def _question_with_history(
    question: str,
    history: tuple[ConversationHistoryItem, ...],
) -> str:
    if not history:
        return question

    history_lines = [
        f"{item.role}: {item.content.strip()}"
        for item in history
        if item.content.strip()
    ]
    if not history_lines:
        return question

    return "\n".join(
        [
            "Recent conversation:",
            *history_lines,
            "",
            f"Current user message: {question}",
        ]
    )


def _context_summary(
    answer_status: str,
    source_count: int,
    message: str | None,
) -> str:
    if answer_status == QUESTION_STATUS_ANSWERED:
        return f"{source_count} source chunk(s) returned."
    if answer_status == QUESTION_STATUS_NO_EVIDENCE:
        return message or "No relevant evidence was found."
    if answer_status == QUESTION_STATUS_NOT_READY:
        return message or "Selected documents are not ready for question answering."
    if answer_status == QUESTION_STATUS_INDEXING_FAILED:
        return message or "Selected documents failed indexing."
    if answer_status == QUESTION_STATUS_INSUFFICIENT_EVIDENCE:
        return message or "Retrieved evidence was insufficient."
    return message or answer_status


def _generation_summary(answer_status: str) -> str:
    if answer_status == QUESTION_STATUS_ANSWERED:
        return "Generated from the configured question-answering workflow."
    return "Skipped because no grounded answer could be generated safely."


def _attachment_context_count(
    attachments: tuple[QuestionAttachment, ...],
) -> int:
    return sum(
        1
        for attachment in attachments
        if attachment.documents or (attachment.text and attachment.text.strip())
    )


def _document_from_legacy_attachment(attachment: QuestionAttachment) -> Document:
    return Document(
        id=str(attachment.document_id),
        text=attachment.text or "",
        source=f"attachment:{attachment.filename}",
        metadata={
            "source": f"attachment:{attachment.filename}",
            "filename": attachment.filename,
            "file_type": _attachment_file_type(attachment.filename),
            "content_type": attachment.content_type,
            "document_id": str(attachment.document_id),
        },
    )


def _attachment_file_type(filename: str) -> str | None:
    suffix = filename.rsplit(".", maxsplit=1)
    if len(suffix) != 2:
        return None
    return suffix[1].lower()


def _lexical_score(question: str, text: str) -> float:
    question_terms = _terms(question) - _STOP_WORDS
    if not question_terms:
        return 1.0

    text_terms = _terms(text)
    if not text_terms:
        return 0.0

    return len(question_terms & text_terms) / len(question_terms)


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "for",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "with",
}
