"""File guide.

- Use: Defines the SQLAlchemy table model for users.
- Usage: Import User from rastin_ai.database.models.user.
- Duties: Defines User and related helper logic.
- Depends on: Project modules: rastin_ai.database.base.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastin_ai.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from rastin_ai.database.models.conversation_session import ConversationSession
    from rastin_ai.database.models.document import Document
    from rastin_ai.database.models.file_metadata import FileMetadata
    from rastin_ai.database.models.organization_member import OrganizationMember
    from rastin_ai.database.models.project_member import ProjectMember
    from rastin_ai.database.models.workflow_execution import WorkflowExecution


class User(TimestampMixin, Base):
    """Foundation user record for future authentication support."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "issuer",
            "external_subject",
            name="uq_users_issuer_external_subject",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    issuer: Mapped[str | None] = mapped_column(String(512), index=True)
    external_subject: Mapped[str | None] = mapped_column(String(512), index=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )

    sessions: Mapped[list[ConversationSession]] = relationship(
        back_populates="user",
    )
    documents: Mapped[list[Document]] = relationship(back_populates="user")
    file_metadata: Mapped[list[FileMetadata]] = relationship(back_populates="user")
    workflow_executions: Mapped[list[WorkflowExecution]] = relationship(
        back_populates="user",
    )
    organization_memberships: Mapped[list[OrganizationMember]] = relationship(
        back_populates="user",
    )
    project_memberships: Mapped[list[ProjectMember]] = relationship(
        back_populates="user",
    )
