"""File guide.

- Use: Defines public API schemas for conversation session endpoints.
- Usage: Import conversation response models from rastin_ai.schemas.conversations.
- Duties: Keeps persisted chat session response contracts separate from services.
- Depends on: External packages only: pydantic, typing, and uuid.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ConversationDocumentReferenceResponse(BaseModel):
    """Logical document reference attached to a conversation message."""

    document_id: UUID
    file_metadata_id: UUID | None = None
    reference_type: str


class ConversationMessageResponse(BaseModel):
    """One ordered conversation turn."""

    id: UUID
    role: str
    sequence: int
    content: str
    workflow_id: UUID | None = None
    status: str
    error_message: str | None = None
    citations: tuple[dict[str, Any], ...] = ()
    sources: tuple[dict[str, Any], ...] = ()
    document_references: tuple[ConversationDocumentReferenceResponse, ...] = ()
    created_at: datetime


class ConversationSessionSummaryResponse(BaseModel):
    """Compact session row for session lists."""

    id: UUID
    title: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class ConversationSessionListResponse(BaseModel):
    """Recent reusable conversation sessions."""

    sessions: tuple[ConversationSessionSummaryResponse, ...]


class ConversationSessionResponse(BaseModel):
    """One reusable conversation session with ordered messages."""

    id: UUID
    title: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    messages: tuple[ConversationMessageResponse, ...] = ()
