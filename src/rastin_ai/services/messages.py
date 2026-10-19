"""File guide.

- Use: Coordinates UI message submission through existing services.
- Usage: Import MessageSubmissionService from rastin_ai.services.messages.
- Duties: Persists attachments, submits questions, and shapes a truthful UI result.
- Depends on: Project modules: rastin_ai.rag.extraction,
  rastin_ai.services.documents, and rastin_ai.services.questions.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import status

from rastin_ai.core.exceptions import AppException
from rastin_ai.database.enums import (
    ConversationMessageRole,
    ConversationMessageStatus,
)
from rastin_ai.observability import (
    observed_span,
    observed_workflow,
    safe_update_observation,
)
from rastin_ai.rag.extraction import (
    DefaultDocumentExtractor,
    DocumentExtractionError,
    DocumentExtractor,
)
from rastin_ai.rag.models import Document
from rastin_ai.repositories.conversations import (
    ConversationDocumentReferenceCreate,
    ConversationMessageCreate,
    ConversationMessageRecord,
    ConversationRepository,
    ConversationSessionRecord,
)
from rastin_ai.services.conversations import (
    ConversationHistoryBuilder,
    ConversationSessionNotFoundError,
)
from rastin_ai.services.documents import (
    DocumentRecord,
    DocumentService,
    DocumentUpload,
)
from rastin_ai.services.questions import (
    QuestionAnswer,
    QuestionAnsweringService,
    QuestionAttachment,
    QuestionInput,
)


class InvalidMessageError(AppException):
    """Raised when a submitted UI message is invalid."""

    def __init__(self, message: str = "Message must not be empty.") -> None:
        super().__init__(
            message,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code="INVALID_MESSAGE",
        )


@dataclass(frozen=True)
class MessageAttachmentInput:
    filename: str
    content: bytes
    content_type: str | None = None


@dataclass(frozen=True)
class MessageAttachmentRecord:
    document_id: UUID
    filename: str
    content_type: str | None
    size_bytes: int
    status: str
    file_metadata_id: UUID | None = None


@dataclass(frozen=True)
class AttachmentExtractionResult:
    documents: tuple[Document, ...]
    text: str | None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class MessageSubmission:
    message: str
    session_id: UUID | None = None
    document_ids: tuple[UUID, ...] = ()
    attachments: tuple[MessageAttachmentInput, ...] = ()


@dataclass(frozen=True)
class MessageSubmissionResult:
    workflow_id: UUID | None
    session_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    status: str
    final_answer: str
    attachments: tuple[MessageAttachmentRecord, ...]
    sources: tuple[dict[str, Any], ...]
    citations: tuple[dict[str, Any], ...]
    artifacts: tuple[dict[str, Any], ...]
    workflow_details: tuple[dict[str, str | None], ...]


class MessageSubmissionService:
    """Submit one UI message without introducing a separate chat domain."""

    def __init__(
        self,
        *,
        document_service: DocumentService,
        question_service: QuestionAnsweringService,
        conversation_repository: ConversationRepository,
        history_builder: ConversationHistoryBuilder,
        user_id: UUID,
        extractor: DocumentExtractor | None = None,
    ) -> None:
        self._document_service = document_service
        self._question_service = question_service
        self._conversation_repository = conversation_repository
        self._history_builder = history_builder
        self._user_id = user_id
        self._extractor = extractor or DefaultDocumentExtractor()

    async def submit(self, submission: MessageSubmission) -> MessageSubmissionResult:
        message = submission.message.strip()
        if not message:
            raise InvalidMessageError()

        with observed_workflow(
            name="message.workflow",
            input={
                "message_chars": len(message),
                "has_session_id": submission.session_id is not None,
                "document_count": len(submission.document_ids),
                "attachment_count": len(submission.attachments),
            },
            metadata={
                "workflow_type": "message_submission",
                "session_id": (
                    str(submission.session_id)
                    if submission.session_id is not None
                    else None
                ),
                "document_ids": [
                    str(document_id) for document_id in submission.document_ids
                ],
            },
            session_id=(
                str(submission.session_id)
                if submission.session_id is not None
                else None
            ),
        ) as observation:
            with observed_span(
                name="message.session.resolve",
                input={"has_session_id": submission.session_id is not None},
            ) as session_observation:
                session = await self._resolve_session(submission.session_id, message)
                safe_update_observation(
                    session_observation,
                    output={"session_id": str(session.id), "status": session.status},
                )
            with observed_span(
                name="message.history.load",
                input={"session_id": str(session.id)},
            ) as history_observation:
                history = await self._history_builder.build(session.id)
                safe_update_observation(
                    history_observation,
                    output={"history_turn_count": len(history)},
                )
            with observed_span(
                name="message.documents.load_references",
                input={"document_count": len(submission.document_ids)},
                metadata={
                    "document_ids": [
                        str(document_id) for document_id in submission.document_ids
                    ]
                },
            ) as reference_observation:
                referenced_documents = await self._load_referenced_documents(
                    submission.document_ids
                )
                safe_update_observation(
                    reference_observation,
                    output={"loaded_document_count": len(referenced_documents)},
                )
            with observed_span(
                name="message.attachments.store",
                input={"attachment_count": len(submission.attachments)},
            ) as attachment_store_observation:
                attachments = await self._store_attachments(submission.attachments)
                safe_update_observation(
                    attachment_store_observation,
                    output={
                        "attachment_document_ids": [
                            str(attachment.document_id) for attachment in attachments
                        ]
                    },
                )
            with observed_span(
                name="message.persist.user",
                input={
                    "session_id": str(session.id),
                    "document_reference_count": len(referenced_documents)
                    + len(attachments),
                },
            ) as user_message_observation:
                user_message = await self._conversation_repository.append_message(
                    ConversationMessageCreate(
                        session_id=session.id,
                        role=ConversationMessageRole.USER,
                        content=message,
                        document_references=_document_references(
                            referenced_documents=referenced_documents,
                            attachments=attachments,
                        ),
                    ),
                    user_id=self._user_id,
                )
                safe_update_observation(
                    user_message_observation,
                    output={"message_id": str(user_message.id)},
                )
            attachment_payload = []
            with observed_span(
                name="message.attachments.extract",
                input={"attachment_count": len(attachments)},
                metadata={
                    "attachment_document_ids": [
                        str(attachment.document_id) for attachment in attachments
                    ]
                },
            ) as extraction_observation:
                for attachment, submission_attachment in zip(
                    attachments,
                    submission.attachments,
                    strict=True,
                ):
                    extraction = _extract_attachment(
                        attachment,
                        submission_attachment,
                        self._extractor,
                    )
                    attachment_payload.append(
                        QuestionAttachment(
                            document_id=attachment.document_id,
                            filename=attachment.filename,
                            content_type=attachment.content_type,
                            size_bytes=attachment.size_bytes,
                            status=attachment.status,
                            text=extraction.text,
                            documents=extraction.documents,
                            extraction_error_code=extraction.error_code,
                            extraction_error_message=extraction.error_message,
                        )
                    )
                safe_update_observation(
                    extraction_observation,
                    output={
                        "extractable_attachment_count": sum(
                            1
                            for attachment in attachment_payload
                            if attachment.documents
                            or (attachment.text is not None and attachment.text.strip())
                        ),
                        "failed_attachment_count": sum(
                            1
                            for attachment in attachment_payload
                            if attachment.extraction_error_code is not None
                        ),
                    },
                )
            try:
                with observed_span(
                    name="message.question_answer",
                    input={
                        "session_id": str(session.id),
                        "document_count": len(submission.document_ids),
                        "attachment_count": len(attachment_payload),
                        "history_turn_count": len(history),
                    },
                ) as answer_observation:
                    answer = await self._question_service.answer(
                        QuestionInput(
                            question=message,
                            document_ids=list(submission.document_ids),
                            attachments=tuple(attachment_payload),
                            session_id=session.id,
                            conversation_history=history,
                        )
                    )
                    safe_update_observation(
                        answer_observation,
                        output={
                            "workflow_id": (
                                str(answer.workflow_id)
                                if answer.workflow_id is not None
                                else None
                            ),
                            "status": answer.status,
                            "source_count": len(answer.sources),
                        },
                    )
            except AppException as exc:
                await self._conversation_repository.append_message(
                    _assistant_error_message_create(
                        session.id,
                        content=exc.message,
                        error_message=exc.message,
                    ),
                    user_id=self._user_id,
                )
                raise
            except Exception:
                await self._conversation_repository.append_message(
                    _assistant_error_message_create(
                        session.id,
                        content="Message processing failed.",
                        error_message="Message processing failed.",
                    ),
                    user_id=self._user_id,
                )
                raise

            with observed_span(
                name="message.persist.workflow_link",
                input={
                    "user_message_id": str(user_message.id),
                    "workflow_id": (
                        str(answer.workflow_id)
                        if answer.workflow_id is not None
                        else None
                    ),
                },
            ) as workflow_link_observation:
                await self._conversation_repository.update_message_workflow(
                    user_message.id,
                    answer.workflow_id,
                    user_id=self._user_id,
                )
                safe_update_observation(
                    workflow_link_observation,
                    output={"status": "linked"},
                )
            with observed_span(
                name="message.persist.assistant",
                input={
                    "session_id": str(session.id),
                    "workflow_id": (
                        str(answer.workflow_id)
                        if answer.workflow_id is not None
                        else None
                    ),
                    "status": answer.status,
                },
            ) as assistant_message_observation:
                assistant_message = await self._conversation_repository.append_message(
                    _assistant_message_create(session.id, answer),
                    user_id=self._user_id,
                )
                safe_update_observation(
                    assistant_message_observation,
                    output={"message_id": str(assistant_message.id)},
                )
            result = _result_from_answer(
                answer,
                session,
                user_message,
                assistant_message,
                attachments,
            )
            safe_update_observation(
                observation,
                output={
                    "session_id": str(result.session_id),
                    "workflow_id": (
                        str(result.workflow_id)
                        if result.workflow_id is not None
                        else None
                    ),
                    "user_message_id": str(result.user_message_id),
                    "assistant_message_id": str(result.assistant_message_id),
                    "status": result.status,
                },
            )
            return result

    async def _resolve_session(
        self,
        session_id: UUID | None,
        message: str,
    ) -> ConversationSessionRecord:
        if session_id is None:
            return await self._conversation_repository.create_session(
                user_id=self._user_id, title=_session_title(message)
            )

        session = await self._conversation_repository.get_session(
            session_id,
            user_id=self._user_id,
        )
        if session is None:
            raise ConversationSessionNotFoundError(session_id)
        return session

    async def _load_referenced_documents(
        self,
        document_ids: tuple[UUID, ...],
    ) -> tuple[DocumentRecord, ...]:
        if not document_ids:
            return ()
        return tuple(await self._document_service.get_documents(list(document_ids)))

    async def _store_attachments(
        self,
        attachments: tuple[MessageAttachmentInput, ...],
    ) -> tuple[MessageAttachmentRecord, ...]:
        records = []
        for attachment in attachments:
            document = await self._document_service.upload_document(
                DocumentUpload(
                    filename=attachment.filename,
                    content=attachment.content,
                    content_type=attachment.content_type,
                )
            )
            records.append(_attachment_from_document(document))

        return tuple(records)


def _attachment_from_document(document: DocumentRecord) -> MessageAttachmentRecord:
    return MessageAttachmentRecord(
        document_id=document.document_id,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        status=document.file_storage_status or document.status,
        file_metadata_id=document.file_metadata_id,
    )


def _result_from_answer(
    answer: QuestionAnswer,
    session: ConversationSessionRecord,
    user_message: ConversationMessageRecord,
    assistant_message: ConversationMessageRecord,
    attachments: tuple[MessageAttachmentRecord, ...],
) -> MessageSubmissionResult:
    return MessageSubmissionResult(
        workflow_id=answer.workflow_id,
        session_id=session.id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        status=answer.status,
        final_answer=answer.answer,
        attachments=attachments,
        sources=answer.sources,
        citations=answer.citations,
        artifacts=(),
        workflow_details=answer.workflow_details,
    )


def _assistant_message_create(
    session_id: UUID,
    answer: QuestionAnswer,
) -> ConversationMessageCreate:
    return ConversationMessageCreate(
        session_id=session_id,
        role=ConversationMessageRole.ASSISTANT,
        content=answer.answer,
        workflow_id=answer.workflow_id,
        status=(
            ConversationMessageStatus.FAILED
            if answer.status == "failed"
            else ConversationMessageStatus.ANSWERED
        ),
        error_message=answer.message if answer.status == "failed" else None,
        citations=answer.citations,
        sources=answer.sources,
        metadata={"answer_status": answer.status, "message": answer.message},
    )


def _assistant_error_message_create(
    session_id: UUID,
    *,
    content: str,
    error_message: str,
) -> ConversationMessageCreate:
    return ConversationMessageCreate(
        session_id=session_id,
        role=ConversationMessageRole.ASSISTANT,
        content=content,
        status=ConversationMessageStatus.FAILED,
        error_message=error_message,
    )


def _document_references(
    *,
    referenced_documents: tuple[DocumentRecord, ...],
    attachments: tuple[MessageAttachmentRecord, ...],
) -> tuple[ConversationDocumentReferenceCreate, ...]:
    references = [
        ConversationDocumentReferenceCreate(
            document_id=document.document_id,
            file_metadata_id=document.file_metadata_id,
            reference_type="referenced",
        )
        for document in referenced_documents
    ]
    references.extend(
        ConversationDocumentReferenceCreate(
            document_id=attachment.document_id,
            file_metadata_id=attachment.file_metadata_id,
            reference_type="attachment",
        )
        for attachment in attachments
    )
    return tuple(references)


def _session_title(message: str) -> str:
    title = " ".join(message.split())
    return title[:80] or "New conversation"


def _extract_attachment(
    attachment: MessageAttachmentRecord,
    source: MessageAttachmentInput,
    extractor: DocumentExtractor,
) -> AttachmentExtractionResult:
    try:
        result = extractor.extract_bytes(
            source.content,
            filename=source.filename,
            source_id=str(attachment.document_id),
            source=f"attachment:{source.filename}",
        )
    except DocumentExtractionError as exc:
        return AttachmentExtractionResult(
            documents=(),
            text=None,
            error_code=exc.code,
            error_message=exc.safe_message,
        )
    except Exception:
        return AttachmentExtractionResult(
            documents=(),
            text=None,
            error_code="EXTRACTION_FAILED",
            error_message="Attachment content could not be extracted.",
        )

    documents = result.documents
    text = "\n\n".join(document.text for document in documents).strip() or None
    return AttachmentExtractionResult(documents=documents, text=text)
