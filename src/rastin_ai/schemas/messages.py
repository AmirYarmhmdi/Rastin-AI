"""File guide.

- Use: Defines public API schemas for message submission endpoints.
- Usage: Import message request and response models from rastin_ai.schemas.messages.
- Duties: Keeps UI-facing message contracts separate from service internals.
- Depends on: External packages only: pydantic, typing, and uuid.
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MessageAttachmentResponse(BaseModel):
    """Metadata for a file attached to a submitted message."""

    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    filename: str
    content_type: str | None = None
    size_bytes: int
    status: str


class WorkflowDetailResponse(BaseModel):
    """Compact UI-safe description of a workflow step."""

    label: str
    status: str
    summary: str | None = None


class MessageSubmissionResponse(BaseModel):
    """Response returned after a message request finishes."""

    workflow_id: UUID | None = None
    session_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    status: str
    final_answer: str
    attachments: tuple[MessageAttachmentResponse, ...] = ()
    sources: tuple[dict[str, Any], ...] = ()
    citations: tuple[dict[str, Any], ...] = ()
    artifacts: tuple[dict[str, Any], ...] = ()
    workflow_details: tuple[WorkflowDetailResponse, ...] = ()
