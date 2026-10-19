"""File guide.

- Use: Defines document/file references attached to conversation messages.
- Usage: Import ConversationMessageDocument from rastin_ai.database.models.
- Duties: Relates turns to logical documents and optional file metadata IDs.
- Depends on: Project modules: rastin_ai.database.base and database models.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rastin_ai.database.base import Base, TimestampMixin

if TYPE_CHECKING:
    from rastin_ai.database.models.conversation_message import ConversationMessage
    from rastin_ai.database.models.document import Document
    from rastin_ai.database.models.file_metadata import FileMetadata


class ConversationMessageDocument(TimestampMixin, Base):
    """Reference between one chat message and one logical document."""

    __tablename__ = "conversation_message_documents"
    __table_args__ = (
        CheckConstraint(
            "reference_type in ('attachment', 'referenced')",
            name="conversation_message_document_reference_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversation_messages.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id"),
        index=True,
        nullable=False,
    )
    file_metadata_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("file_metadata.id"),
        index=True,
    )
    reference_type: Mapped[str] = mapped_column(String(32), nullable=False)

    message: Mapped[ConversationMessage] = relationship(
        back_populates="document_references",
    )
    document: Mapped[Document] = relationship()
    file_metadata: Mapped[FileMetadata | None] = relationship()
