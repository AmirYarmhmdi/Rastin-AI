"""SQLAlchemy model for projects."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastin_ai.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from rastin_ai.database.models.conversation_session import ConversationSession
    from rastin_ai.database.models.document import Document
    from rastin_ai.database.models.organization import Organization
    from rastin_ai.database.models.project_member import ProjectMember
    from rastin_ai.database.models.user import User


class Project(TimestampMixin, Base):
    """Organization-scoped project workspace."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            name="uq_projects_id_organization_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    organization: Mapped[Organization] = relationship(back_populates="projects")
    created_by: Mapped[User] = relationship()
    members: Mapped[list[ProjectMember]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="project",
        overlaps="organization",
    )
    sessions: Mapped[list[ConversationSession]] = relationship(
        back_populates="project",
        overlaps="organization",
    )
