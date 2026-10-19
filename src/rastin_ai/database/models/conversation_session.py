"""File guide.

- Use: Defines the SQLAlchemy table model for conversation sessions.
- Usage: Import ConversationSession from
  rastin_ai.database.models.conversation_session.
- Duties: Defines ConversationSession and related helper logic.
- Depends on: Project modules: rastin_ai.database.base, and
  rastin_ai.database.enums.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastin_ai.database.base import Base, TimestampMixin
from rastin_ai.database.enums import ConversationSessionStatus

if TYPE_CHECKING:
    from rastin_ai.database.models.conversation_message import ConversationMessage
    from rastin_ai.database.models.document import Document
    from rastin_ai.database.models.organization import Organization
    from rastin_ai.database.models.project import Project
    from rastin_ai.database.models.user import User
    from rastin_ai.database.models.workflow_execution import WorkflowExecution


class ConversationSession(TimestampMixin, Base):
    """Rastin-AI application session, not a SQLAlchemy DB session."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "status in ('active', 'archived')",
            name="session_status",
        ),
        CheckConstraint(
            "(organization_id is null and project_id is null) or "
            "(organization_id is not null and project_id is not null)",
            name="session_project_scope_pair",
        ),
        ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["projects.id", "projects.organization_id"],
        ),
        Index(
            "ix_sessions_organization_id_project_id",
            "organization_id",
            "project_id",
        ),
        Index(
            "ix_sessions_project_user_updated_at",
            "organization_id",
            "project_id",
            "user_id",
            "updated_at",
        ),
        UniqueConstraint(
            "id",
            "organization_id",
            "project_id",
            name="uq_sessions_id_organization_id_project_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(255))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=ConversationSessionStatus.ACTIVE.value,
        server_default=ConversationSessionStatus.ACTIVE.value,
        nullable=False,
    )

    user: Mapped[User | None] = relationship(back_populates="sessions")
    organization: Mapped[Organization | None] = relationship()
    project: Mapped[Project | None] = relationship(
        back_populates="sessions",
        overlaps="organization",
    )
    documents: Mapped[list[Document]] = relationship(back_populates="session")
    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.sequence",
    )
    workflow_executions: Mapped[list[WorkflowExecution]] = relationship(
        back_populates="session",
        foreign_keys="WorkflowExecution.session_id",
    )
