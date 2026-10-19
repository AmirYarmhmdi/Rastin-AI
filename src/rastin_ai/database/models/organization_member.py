"""SQLAlchemy model for organization membership."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastin_ai.database.base import Base, TimestampMixin
from rastin_ai.database.enums import OrganizationMemberRole

if TYPE_CHECKING:
    from rastin_ai.database.models.organization import Organization
    from rastin_ai.database.models.user import User


class OrganizationMember(TimestampMixin, Base):
    """One user's fixed role in one organization."""

    __tablename__ = "organization_members"
    __table_args__ = (
        CheckConstraint(
            "role in ('OWNER', 'MEMBER')",
            name="organization_member_role",
        ),
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_members_organization_id_user_id",
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
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        default=OrganizationMemberRole.MEMBER.value,
        server_default=OrganizationMemberRole.MEMBER.value,
        nullable=False,
    )

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="organization_memberships")
