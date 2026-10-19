"""File guide.

- Use: Defines the SQLAlchemy table model for workflow executions.
- Usage: Import WorkflowExecution from
  rastin_ai.database.models.workflow_execution.
- Duties: Defines WorkflowExecution and related helper logic.
- Depends on: Project modules: rastin_ai.database.base, and
  rastin_ai.database.enums.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastin_ai.database.base import Base, TimestampMixin
from rastin_ai.database.enums import WorkflowExecutionStatus

if TYPE_CHECKING:
    from rastin_ai.database.models.conversation_message import ConversationMessage
    from rastin_ai.database.models.conversation_session import ConversationSession
    from rastin_ai.database.models.organization import Organization
    from rastin_ai.database.models.project import Project
    from rastin_ai.database.models.user import User


class WorkflowExecution(TimestampMixin, Base):
    """High-level workflow execution state for Rastin-AI."""

    __tablename__ = "workflow_executions"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'running', 'completed', 'failed')",
            name="workflow_execution_status",
        ),
        CheckConstraint(
            "(organization_id is null and project_id is null) or "
            "(organization_id is not null and project_id is not null)",
            name="workflow_execution_project_scope_pair",
        ),
        ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["projects.id", "projects.organization_id"],
        ),
        ForeignKeyConstraint(
            ["session_id", "organization_id", "project_id"],
            ["sessions.id", "sessions.organization_id", "sessions.project_id"],
            name="fk_workflow_executions_session_project_scope",
        ),
        Index(
            "ix_workflow_executions_organization_id_project_id",
            "organization_id",
            "project_id",
        ),
        Index(
            "ix_workflow_executions_project_session_user",
            "organization_id",
            "project_id",
            "session_id",
            "user_id",
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
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        index=True,
    )
    workflow_name: Mapped[str] = mapped_column(String(255), nullable=False)
    workflow_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(32),
        default=WorkflowExecutionStatus.PENDING.value,
        server_default=WorkflowExecutionStatus.PENDING.value,
        nullable=False,
        index=True,
    )
    input_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[ConversationSession] = relationship(
        back_populates="workflow_executions",
        foreign_keys=[session_id],
    )
    user: Mapped[User | None] = relationship(back_populates="workflow_executions")
    organization: Mapped[Organization | None] = relationship()
    project: Mapped[Project | None] = relationship(overlaps="organization")
    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="workflow"
    )
