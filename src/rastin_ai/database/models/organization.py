"""SQLAlchemy model for organizations."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastin_ai.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from rastin_ai.database.models.organization_member import OrganizationMember
    from rastin_ai.database.models.project import Project
    from rastin_ai.database.models.user import User


class Organization(TimestampMixin, Base):
    """Company or team workspace container."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    created_by: Mapped[User] = relationship()
    members: Mapped[list[OrganizationMember]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
