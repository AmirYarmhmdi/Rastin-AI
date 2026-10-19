"""File guide.

- Use: Defines the SQLAlchemy table model for uploaded file metadata.
- Usage: Import FileMetadata from rastin_ai.database.models.file_metadata.
- Duties: Defines FileMetadata and related helper logic.
- Depends on: Project modules: rastin_ai.database.base, and
  rastin_ai.database.enums.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastin_ai.database.base import Base, TimestampMixin
from rastin_ai.database.enums import FileStorageStatus

if TYPE_CHECKING:
    from rastin_ai.database.models.document import Document
    from rastin_ai.database.models.user import User


class FileMetadata(TimestampMixin, Base):
    """Metadata for the physical source file behind a document."""

    __tablename__ = "file_metadata"
    __table_args__ = (
        CheckConstraint(
            "size_bytes >= 0",
            name="file_metadata_size_bytes_non_negative",
        ),
        CheckConstraint(
            "status in ('stored', 'failed')",
            name="file_metadata_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id"),
        unique=True,
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255))
    normalized_extension: Mapped[str] = mapped_column(String(16), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=FileStorageStatus.STORED.value,
        server_default=FileStorageStatus.STORED.value,
        nullable=False,
    )
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))

    document: Mapped[Document | None] = relationship(back_populates="file_metadata")
    user: Mapped[User | None] = relationship(back_populates="file_metadata")
