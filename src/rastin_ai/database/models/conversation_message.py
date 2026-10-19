"""File guide.

- Use: Defines persisted ordered conversation messages.
- Usage: Import ConversationMessage from rastin_ai.database.models.
- Duties: Stores chat turns, assistant status, workflow links, and safe citations.
- Depends on: Project modules: rastin_ai.database.base and database enums.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastin_ai.database.base import Base, TimestampMixin
from rastin_ai.database.enums import (
    ConversationMessageStatus,
)

if TYPE_CHECKING:
    from rastin_ai.database.models.conversation_message_document import (
        ConversationMessageDocument,
    )
    from rastin_ai.database.models.conversation_session import ConversationSession
    from rastin_ai.database.models.workflow_execution import WorkflowExecution


class ConversationMessage(TimestampMixin, Base):
    """A durable user or assistant turn in a reusable conversation session."""

    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint(
            "role in ('user', 'assistant')",
            name="conversation_message_role",
        ),
        CheckConstraint(
            "status in ('submitted', 'answered', 'failed')",
            name="conversation_message_status",
        ),
        UniqueConstraint(
            "session_id",
            "sequence",
            name="uq_conversation_messages_session_sequence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
        index=True,
        nullable=False,
    )
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_executions.id"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=ConversationMessageStatus.SUBMITTED.value,
        server_default=ConversationMessageStatus.SUBMITTED.value,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(String(512))
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        server_default="[]",
        nullable=False,
    )
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        server_default="[]",
        nullable=False,
    )
    message_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    session: Mapped[ConversationSession] = relationship(back_populates="messages")
    workflow: Mapped[WorkflowExecution | None] = relationship(
        back_populates="messages",
    )
    document_references: Mapped[list[ConversationMessageDocument]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )
