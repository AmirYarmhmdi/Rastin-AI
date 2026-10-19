"""Project-scoped private chat endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from rastin_ai.api.dependencies import (
    get_project_access_context,
    get_project_conversation_service,
    get_project_message_submission_service,
    get_project_workflow_status_service,
)
from rastin_ai.schemas.messages import (
    MessageAttachmentResponse,
    WorkflowDetailResponse,
)
from rastin_ai.schemas.project_conversations import (
    ProjectMessageResponse,
    ProjectMessageSubmissionResponse,
    ProjectSessionCreateRequest,
    ProjectSessionListResponse,
    ProjectSessionResponse,
    ProjectSessionSummaryResponse,
    ProjectWorkflowStatusResponse,
)
from rastin_ai.services.authorization import ProjectAccessContext
from rastin_ai.services.conversations import (
    ConversationMessageView,
    ConversationSessionSummary,
    ConversationSessionView,
    ProjectConversationService,
)
from rastin_ai.services.documents import InvalidDocumentUploadError
from rastin_ai.services.messages import InvalidMessageError, MessageAttachmentInput
from rastin_ai.services.project_messages import (
    ProjectMessageSubmission,
    ProjectMessageSubmissionResult,
    ProjectMessageSubmissionService,
)
from rastin_ai.services.project_workflows import ProjectWorkflowStatusService

router = APIRouter(prefix="/projects/{project_id}/sessions")


@router.post(
    "",
    response_model=ProjectSessionSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create private project chat",
)
async def create_project_session(
    request: ProjectSessionCreateRequest,
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    conversation_service: Annotated[
        ProjectConversationService,
        Depends(get_project_conversation_service),
    ],
) -> ProjectSessionSummaryResponse:
    session = await conversation_service.create_session(context, title=request.title)
    return _session_summary_response(session)


@router.get(
    "",
    response_model=ProjectSessionListResponse,
    summary="List private project chats",
)
async def list_project_sessions(
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    conversation_service: Annotated[
        ProjectConversationService,
        Depends(get_project_conversation_service),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ProjectSessionListResponse:
    sessions = await conversation_service.list_sessions(context, limit=limit)
    return ProjectSessionListResponse(
        sessions=tuple(_session_summary_response(session) for session in sessions)
    )


@router.get(
    "/{session_id}",
    response_model=ProjectSessionResponse,
    summary="Get private project chat",
)
async def get_project_session(
    session_id: UUID,
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    conversation_service: Annotated[
        ProjectConversationService,
        Depends(get_project_conversation_service),
    ],
) -> ProjectSessionResponse:
    session = await conversation_service.get_session(context, session_id)
    return _session_response(session)


@router.post(
    "/{session_id}/messages",
    response_model=ProjectMessageSubmissionResponse,
    summary="Submit project chat message",
)
async def submit_project_message(
    session_id: UUID,
    message: Annotated[str, Form(min_length=1)],
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    message_service: Annotated[
        ProjectMessageSubmissionService,
        Depends(get_project_message_submission_service),
    ],
    files: Annotated[
        list[UploadFile] | None,
        File(description="Optional files attached only to this project chat."),
    ] = None,
) -> ProjectMessageSubmissionResponse:
    normalized_message = message.strip()
    if not normalized_message:
        raise InvalidMessageError()

    attachments = await _read_attachments(files or [])
    result = await message_service.submit(
        context,
        ProjectMessageSubmission(
            message=normalized_message,
            session_id=session_id,
            attachments=tuple(attachments),
        ),
    )
    return _message_submission_response(result)


@router.get(
    "/{session_id}/workflows/{workflow_id}",
    response_model=ProjectWorkflowStatusResponse,
    summary="Get private project chat workflow status",
)
async def get_project_workflow_status(
    session_id: UUID,
    workflow_id: UUID,
    context: Annotated[ProjectAccessContext, Depends(get_project_access_context)],
    workflow_service: Annotated[
        ProjectWorkflowStatusService,
        Depends(get_project_workflow_status_service),
    ],
) -> ProjectWorkflowStatusResponse:
    workflow = await workflow_service.get_workflow_status(
        context,
        session_id=session_id,
        workflow_id=workflow_id,
    )
    return ProjectWorkflowStatusResponse(
        workflow_id=workflow.workflow_id,
        session_id=workflow.session_id,
        status=workflow.status,
        result=workflow.result,
        error=workflow.error,
        trace_id=workflow.trace_id,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
        started_at=workflow.started_at,
        finished_at=workflow.finished_at,
    )


async def _read_attachments(files: list[UploadFile]) -> list[MessageAttachmentInput]:
    attachments = []
    for file in files:
        if not file.filename:
            raise InvalidDocumentUploadError("Uploaded document filename is required.")

        attachments.append(
            MessageAttachmentInput(
                filename=file.filename,
                content=await file.read(),
                content_type=file.content_type,
            )
        )

    return attachments


def _session_summary_response(
    session: ConversationSessionSummary,
) -> ProjectSessionSummaryResponse:
    return ProjectSessionSummaryResponse(
        id=session.id,
        title=session.title,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _session_response(session: ConversationSessionView) -> ProjectSessionResponse:
    return ProjectSessionResponse(
        id=session.id,
        title=session.title,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=tuple(_message_response(message) for message in session.messages),
    )


def _message_response(message: ConversationMessageView) -> ProjectMessageResponse:
    return ProjectMessageResponse(
        id=message.id,
        role=message.role,
        sequence=message.sequence,
        content=message.content,
        workflow_id=message.workflow_id,
        status=message.status,
        error_message=message.error_message,
        citations=message.citations,
        sources=message.sources,
        document_references=message.document_references,
        created_at=message.created_at,
    )


def _message_submission_response(
    result: ProjectMessageSubmissionResult,
) -> ProjectMessageSubmissionResponse:
    return ProjectMessageSubmissionResponse(
        workflow_id=result.workflow_id,
        session_id=result.session_id,
        user_message=ProjectMessageResponse(
            id=result.user_message.id,
            role=result.user_message.role,
            sequence=result.user_message.sequence,
            content=result.user_message.content,
            workflow_id=result.user_message.workflow_id,
            status=result.user_message.status,
            error_message=result.user_message.error_message,
            citations=result.user_message.citations,
            sources=result.user_message.sources,
            document_references=tuple(
                {
                    "document_id": reference.document_id,
                    "file_metadata_id": reference.file_metadata_id,
                    "reference_type": reference.reference_type,
                }
                for reference in result.user_message.document_references
            ),
            created_at=result.user_message.created_at,
        ),
        assistant_message=ProjectMessageResponse(
            id=result.assistant_message.id,
            role=result.assistant_message.role,
            sequence=result.assistant_message.sequence,
            content=result.assistant_message.content,
            workflow_id=result.assistant_message.workflow_id,
            status=result.assistant_message.status,
            error_message=result.assistant_message.error_message,
            citations=result.assistant_message.citations,
            sources=result.assistant_message.sources,
            document_references=(),
            created_at=result.assistant_message.created_at,
        ),
        status=result.status,
        final_answer=result.final_answer,
        attachments=tuple(
            MessageAttachmentResponse(
                document_id=attachment.document_id,
                filename=attachment.filename,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                status=attachment.status,
            )
            for attachment in result.attachments
        ),
        sources=result.sources,
        citations=result.citations,
        workflow_details=tuple(
            WorkflowDetailResponse(
                label=detail["label"] or "",
                status=detail["status"] or "",
                summary=detail.get("summary"),
            )
            for detail in result.workflow_details
        ),
    )
