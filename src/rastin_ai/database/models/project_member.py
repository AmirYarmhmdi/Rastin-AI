"""SQLAlchemy model for project membership."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastin_ai.database.base import Base, TimestampMixin
from rastin_ai.database.enums import ProjectMemberRole

if TYPE_CHECKING:
    from rastin_ai.database.models.project import Project
    from rastin_ai.database.models.user import User


class ProjectMember(TimestampMixin, Base):
    """One user's fixed role in one project."""

    __tablename__ = "project_members"
    __table_args__ = (
        CheckConstraint(
            "role in ('ADMIN', 'MEMBER', 'VIEWER')",
            name="project_member_role",
        ),
        UniqueConstraint(
            "project_id",
            "user_id",
            name="uq_project_members_project_id_user_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        default=ProjectMemberRole.MEMBER.value,
        server_default=ProjectMemberRole.MEMBER.value,
        nullable=False,
    )

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="project_memberships")
