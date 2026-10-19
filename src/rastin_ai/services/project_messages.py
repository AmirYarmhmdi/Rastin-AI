"""Project-scoped private chat message submission."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from rastin_ai.database.enums import ConversationMessageRole
from rastin_ai.repositories.conversations import (
    ConversationDocumentReferenceCreate,
    ConversationMessageCreate,
    ConversationMessageRecord,
    ConversationRepository,
)
from rastin_ai.repositories.project_documents import ProjectDocumentRecord
from rastin_ai.services.authorization import (
    PROJECT_PERMISSION_CHATS_CREATE,
    AuthorizationService,
    ProjectAccessContext,
)
from rastin_ai.services.conversations import (
    ConversationSessionNotFoundError,
    ProjectConversationHistoryBuilder,
)
from rastin_ai.services.messages import (
    InvalidMessageError,
    MessageAttachmentInput,
    MessageAttachmentRecord,
    _assistant_error_message_create,
    _assistant_message_create,
)
from rastin_ai.services.project_documents import (
    ProjectDocumentService,
    ProjectDocumentUpload,
)
from rastin_ai.services.questions import (
    ProjectRetrievalScope,
    QuestionAnsweringService,
    QuestionInput,
)


@dataclass(frozen=True)
class ProjectMessageSubmission:
    message: str
    session_id: UUID
    attachments: tuple[MessageAttachmentInput, ...] = ()


@dataclass(frozen=True)
class ProjectMessageSubmissionResult:
    workflow_id: UUID | None
    session_id: UUID
    user_message: ConversationMessageRecord
    assistant_message: ConversationMessageRecord
    status: str
    final_answer: str
    attachments: tuple[MessageAttachmentRecord, ...]
    sources: tuple[dict[str, Any], ...]
    citations: tuple[dict[str, Any], ...]
    workflow_details: tuple[dict[str, str | None], ...]


class ProjectMessageSubmissionService:
    """Submit one message to an owned private project chat."""

    def __init__(
        self,
        *,
        conversation_repository: ConversationRepository,
        history_builder: ProjectConversationHistoryBuilder,
        project_document_service: ProjectDocumentService,
        question_service: QuestionAnsweringService,
        authorization_service: AuthorizationService,
    ) -> None:
        self._conversation_repository = conversation_repository
        self._history_builder = history_builder
        self._project_document_service = project_document_service
        self._question_service = question_service
        self._authorization_service = authorization_service

    async def submit(
        self,
        context: ProjectAccessContext,
        submission: ProjectMessageSubmission,
    ) -> ProjectMessageSubmissionResult:
        self._authorization_service.require_project_permission(
            context,
            PROJECT_PERMISSION_CHATS_CREATE,
        )
        message = submission.message.strip()
        if not message:
            raise InvalidMessageError()

        session = await self._conversation_repository.get_project_session_with_messages(
            submission.session_id,
            user_id=context.principal.user_id,
            organization_id=context.organization.id,
            project_id=context.project.id,
        )
        if session is None:
            raise ConversationSessionNotFoundError(submission.session_id)

        history = await self._history_builder.build(context, submission.session_id)
        attachments = await self._store_attachments(context, submission)
        user_message = await self._conversation_repository.append_project_message(
            ConversationMessageCreate(
                session_id=session.id,
                role=ConversationMessageRole.USER,
                content=message,
                document_references=_attachment_references(attachments),
            ),
            user_id=context.principal.user_id,
            organization_id=context.organization.id,
            project_id=context.project.id,
        )

        try:
            answer = await self._question_service.answer(
                QuestionInput(
                    question=message,
                    document_ids=[],
                    session_id=session.id,
                    conversation_history=history,
                    project_retrieval_scope=ProjectRetrievalScope(
                        organization_id=context.organization.id,
                        project_id=context.project.id,
                        session_id=session.id,
                    ),
                )
            )
        except Exception:
            await self._conversation_repository.append_project_message(
                _assistant_error_message_create(
                    session.id,
                    content="Message processing failed.",
                    error_message="Message processing failed.",
                ),
                user_id=context.principal.user_id,
                organization_id=context.organization.id,
                project_id=context.project.id,
            )
            raise

        await self._conversation_repository.update_project_message_workflow(
            user_message.id,
            answer.workflow_id,
            user_id=context.principal.user_id,
            organization_id=context.organization.id,
            project_id=context.project.id,
        )
        assistant_message = await self._conversation_repository.append_project_message(
            _assistant_message_create(session.id, answer),
            user_id=context.principal.user_id,
            organization_id=context.organization.id,
            project_id=context.project.id,
        )
        return ProjectMessageSubmissionResult(
            workflow_id=answer.workflow_id,
            session_id=session.id,
            user_message=user_message,
            assistant_message=assistant_message,
            status=answer.status,
            final_answer=answer.answer,
            attachments=attachments,
            sources=answer.sources,
            citations=answer.citations,
            workflow_details=answer.workflow_details,
        )

    async def _store_attachments(
        self,
        context: ProjectAccessContext,
        submission: ProjectMessageSubmission,
    ) -> tuple[MessageAttachmentRecord, ...]:
        records = []
        for attachment in submission.attachments:
            upload_attachment = (
                self._project_document_service.upload_chat_attachment_document
            )
            document = await upload_attachment(
                context,
                submission.session_id,
                ProjectDocumentUpload(
                    filename=attachment.filename,
                    content=attachment.content,
                    content_type=attachment.content_type,
                ),
            )
            records.append(_attachment_from_project_document(document))
        return tuple(records)


def _attachment_from_project_document(
    document: ProjectDocumentRecord,
) -> MessageAttachmentRecord:
    return MessageAttachmentRecord(
        document_id=document.document_id,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        status=document.file_storage_status or document.status,
        file_metadata_id=document.file_metadata_id,
    )


def _attachment_references(
    attachments: tuple[MessageAttachmentRecord, ...],
) -> tuple[ConversationDocumentReferenceCreate, ...]:
    return tuple(
        ConversationDocumentReferenceCreate(
            document_id=attachment.document_id,
            file_metadata_id=attachment.file_metadata_id,
            reference_type="attachment",
        )
        for attachment in attachments
    )
