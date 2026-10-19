"""File guide.

- Use: Defines the SQLAlchemy table model for documents.
- Usage: Import Document from rastin_ai.database.models.document.
- Duties: Defines Document and related helper logic.
- Depends on: Project modules: rastin_ai.database.base, and
  rastin_ai.database.enums.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastin_ai.database.base import Base, TimestampMixin
from rastin_ai.database.enums import DocumentScope, DocumentStatus

if TYPE_CHECKING:
    from rastin_ai.database.models.conversation_session import ConversationSession
    from rastin_ai.database.models.file_metadata import FileMetadata
    from rastin_ai.database.models.organization import Organization
    from rastin_ai.database.models.project import Project
    from rastin_ai.database.models.user import User


class Document(TimestampMixin, Base):
    """Logical document within an Rastin-AI session."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status in ('uploaded', 'processing', 'indexed', 'failed')",
            name="document_status",
        ),
        CheckConstraint(
            "document_scope in ('LEGACY', 'PROJECT_LIBRARY', 'CHAT_ATTACHMENT')",
            name="document_scope",
        ),
        CheckConstraint(
            "("
            "document_scope = 'LEGACY' "
            "and session_id is not null "
            "and organization_id is null "
            "and project_id is null"
            ") or ("
            "document_scope = 'PROJECT_LIBRARY' "
            "and session_id is null "
            "and organization_id is not null "
            "and project_id is not null"
            ") or ("
            "document_scope = 'CHAT_ATTACHMENT' "
            "and session_id is not null "
            "and organization_id is not null "
            "and project_id is not null"
            ")",
            name="document_scope_ownership",
        ),
        ForeignKeyConstraint(
            ["project_id", "organization_id"],
            ["projects.id", "projects.organization_id"],
        ),
        Index(
            "ix_documents_organization_id_project_id",
            "organization_id",
            "project_id",
        ),
        Index(
            "ix_documents_project_scope",
            "organization_id",
            "project_id",
            "document_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id"),
        index=True,
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        index=True,
    )
    document_scope: Mapped[str] = mapped_column(
        String(32),
        default=DocumentScope.LEGACY.value,
        server_default=DocumentScope.LEGACY.value,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=DocumentStatus.UPLOADED.value,
        server_default=DocumentStatus.UPLOADED.value,
        nullable=False,
    )
    indexing_error_code: Mapped[str | None] = mapped_column(String(64))
    indexing_error_message: Mapped[str | None] = mapped_column(String(512))

    session: Mapped[ConversationSession | None] = relationship(
        back_populates="documents"
    )
    user: Mapped[User | None] = relationship(back_populates="documents")
    organization: Mapped[Organization | None] = relationship()
    project: Mapped[Project | None] = relationship(
        back_populates="documents",
        overlaps="organization",
    )
    file_metadata: Mapped[FileMetadata | None] = relationship(
        back_populates="document",
        uselist=False,
    )
