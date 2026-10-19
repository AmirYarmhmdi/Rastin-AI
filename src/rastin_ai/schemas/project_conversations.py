"""Project-scoped private chat API schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from rastin_ai.schemas.messages import (
    MessageAttachmentResponse,
    WorkflowDetailResponse,
)


class ProjectSessionCreateRequest(BaseModel):
    """Create a private project chat session."""

    title: str | None = Field(default=None, max_length=255)


class ProjectMessageResponse(BaseModel):
    """One owner-authorized project chat message."""

    id: UUID
    role: str
    sequence: int
    content: str
    workflow_id: UUID | None = None
    status: str
    error_message: str | None = None
    citations: tuple[dict[str, Any], ...] = ()
    sources: tuple[dict[str, Any], ...] = ()
    document_references: tuple[dict[str, UUID | str | None], ...] = ()
    created_at: datetime


class ProjectSessionSummaryResponse(BaseModel):
    """Safe private project chat metadata."""

    id: UUID
    title: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectSessionListResponse(BaseModel):
    """Private project chats for the current user."""

    sessions: tuple[ProjectSessionSummaryResponse, ...]


class ProjectSessionResponse(BaseModel):
    """Safe project chat metadata with bounded message history."""

    id: UUID
    title: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    messages: tuple[ProjectMessageResponse, ...] = ()


class ProjectMessageSubmissionResponse(BaseModel):
    """Response returned after a project chat message finishes."""

    workflow_id: UUID | None = None
    session_id: UUID
    user_message: ProjectMessageResponse
    assistant_message: ProjectMessageResponse
    status: str
    final_answer: str
    attachments: tuple[MessageAttachmentResponse, ...] = ()
    sources: tuple[dict[str, Any], ...] = ()
    citations: tuple[dict[str, Any], ...] = ()
    workflow_details: tuple[WorkflowDetailResponse, ...] = ()


class ProjectWorkflowStatusResponse(BaseModel):
    """Project-scoped workflow execution status."""

    model_config = ConfigDict(from_attributes=True)

    workflow_id: UUID
    session_id: UUID
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    trace_id: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
