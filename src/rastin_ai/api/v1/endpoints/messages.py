"""File guide.

- Use: Serves UI message submission API endpoints.
- Usage: Included by rastin_ai.api.v1.router.
- Duties: Accepts multipart message requests and delegates orchestration to services.
- Depends on: External packages: fastapi. Project modules:
  rastin_ai.api.dependencies, schemas.messages, and services.messages.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile

from rastin_ai.api.dependencies import get_message_submission_service
from rastin_ai.schemas.messages import (
    MessageAttachmentResponse,
    MessageSubmissionResponse,
    WorkflowDetailResponse,
)
from rastin_ai.services.documents import InvalidDocumentUploadError
from rastin_ai.services.messages import (
    InvalidMessageError,
    MessageAttachmentInput,
    MessageSubmission,
    MessageSubmissionService,
)

router = APIRouter(prefix="/messages")


@router.post(
    "",
    response_model=MessageSubmissionResponse,
    summary="Submit message",
)
async def submit_message(
    message: Annotated[str, Form(min_length=1)],
    message_service: Annotated[
        MessageSubmissionService,
        Depends(get_message_submission_service),
    ],
    session_id: Annotated[UUID | None, Form()] = None,
    document_ids: Annotated[
        list[UUID] | None,
        Form(description="Optional logical document IDs to scope retrieval."),
    ] = None,
    files: Annotated[
        list[UploadFile] | None,
        File(description="Optional files attached to this message."),
    ] = None,
) -> MessageSubmissionResponse:
    normalized_message = message.strip()
    if not normalized_message:
        raise InvalidMessageError()

    attachments = await _read_attachments(files or [])
    result = await message_service.submit(
        MessageSubmission(
            message=normalized_message,
            session_id=session_id,
            document_ids=tuple(document_ids or ()),
            attachments=tuple(attachments),
        )
    )
    return MessageSubmissionResponse(
        workflow_id=result.workflow_id,
        session_id=result.session_id,
        user_message_id=result.user_message_id,
        assistant_message_id=result.assistant_message_id,
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
        artifacts=result.artifacts,
        workflow_details=tuple(
            WorkflowDetailResponse(
                label=detail["label"] or "",
                status=detail["status"] or "",
                summary=detail.get("summary"),
            )
            for detail in result.workflow_details
        ),
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
