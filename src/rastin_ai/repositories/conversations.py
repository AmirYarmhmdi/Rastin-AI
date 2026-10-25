"""File guide.

- Use: Persists reusable conversation sessions, ordered messages, and references.
- Usage: Import ConversationRepository and SQLAlchemyConversationRepository.
- Duties: Keeps PostgreSQL as the source of truth for chat history.
- Depends on: External package sqlalchemy. Project modules: database enums/models.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from rastin_ai.database.enums import (
    ConversationMessageRole,
    ConversationMessageStatus,
    ConversationSessionStatus,
)
from rastin_ai.database.models.conversation_message import ConversationMessage
from rastin_ai.database.models.conversation_message_document import (
    ConversationMessageDocument,
)
from rastin_ai.database.models.conversation_session import ConversationSession


@dataclass(frozen=True)
class ConversationDocumentReferenceCreate:
    document_id: UUID
    file_metadata_id: UUID | None
    reference_type: str


@dataclass(frozen=True)
class ConversationDocumentReferenceRecord:
    id: UUID
    message_id: UUID
    document_id: UUID
    file_metadata_id: UUID | None
    reference_type: str
    created_at: datetime


@dataclass(frozen=True)
class ConversationMessageCreate:
    session_id: UUID
    role: ConversationMessageRole
    content: str
    workflow_id: UUID | None = None
    status: ConversationMessageStatus = ConversationMessageStatus.SUBMITTED
    error_message: str | None = None
    citations: tuple[dict[str, Any], ...] = ()
    sources: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] | None = None
    document_references: tuple[ConversationDocumentReferenceCreate, ...] = ()


@dataclass(frozen=True)
class ConversationMessageRecord:
    id: UUID
    session_id: UUID
    role: str
    sequence: int
    content: str
    workflow_id: UUID | None
    status: str
    error_message: str | None
    citations: tuple[dict[str, Any], ...]
    sources: tuple[dict[str, Any], ...]
    metadata: dict[str, Any]
    document_references: tuple[ConversationDocumentReferenceRecord, ...]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ConversationSessionRecord:
    user_id: UUID | None
    id: UUID
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    organization_id: UUID | None = None
    project_id: UUID | None = None
    messages: tuple[ConversationMessageRecord, ...] = ()


class ConversationRepository(Protocol):
    async def rename_project_session(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
        title: str,
    ) -> ConversationSessionRecord | None:
        """Rename a private project session belonging to the current user."""

    async def create_session(
        self, *, user_id: UUID, title: str | None = None
    ) -> ConversationSessionRecord:
        """Create a reusable conversation session."""

    async def create_project_session(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
        title: str | None = None,
    ) -> ConversationSessionRecord:
        """Create a private project-scoped conversation session."""

    async def get_session(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
    ) -> ConversationSessionRecord | None:
        """Return a session without messages."""

    async def get_session_with_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
    ) -> ConversationSessionRecord | None:
        """Return one session and ordered messages."""

    async def get_project_session_with_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
    ) -> ConversationSessionRecord | None:
        """Return one project session and ordered messages for its owner."""

    async def list_sessions(
        self,
        *,
        user_id: UUID,
        limit: int,
    ) -> list[ConversationSessionRecord]:
        """Return recent reusable conversation sessions."""

    async def list_project_sessions(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
        limit: int,
    ) -> list[ConversationSessionRecord]:
        """Return recent private sessions in one project."""

    async def append_message(
        self,
        message: ConversationMessageCreate,
        *,
        user_id: UUID,
    ) -> ConversationMessageRecord:
        """Append one ordered message to a session."""

    async def append_project_message(
        self,
        message: ConversationMessageCreate,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
    ) -> ConversationMessageRecord:
        """Append one ordered message to a project session."""

    async def update_message_workflow(
        self,
        message_id: UUID,
        workflow_id: UUID | None,
        *,
        user_id: UUID,
    ) -> ConversationMessageRecord:
        """Attach a workflow ID to an already-persisted message."""

    async def update_project_message_workflow(
        self,
        message_id: UUID,
        workflow_id: UUID | None,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
    ) -> ConversationMessageRecord:
        """Attach a workflow ID to an owned project message."""

    async def recent_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
        limit: int,
    ) -> list[ConversationMessageRecord]:
        """Return recent messages in chronological order."""

    async def recent_project_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
        limit: int,
    ) -> list[ConversationMessageRecord]:
        """Return recent project-session messages in chronological order."""


class SQLAlchemyConversationRepository:
    """SQLAlchemy-backed reusable conversation repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def rename_project_session(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
        title: str,
    ) -> ConversationSessionRecord | None:
        record = await self._get_project_session_model(
            session_id,
            user_id=user_id,
            organization_id=organization_id,
            project_id=project_id,
        )
        if record is None:
            return None
        record.title = title
        await self._commit_and_refresh(record)
        return _session_record(record)

    async def create_session(
        self,
        *,
        user_id: UUID,
        title: str | None = None,
    ) -> ConversationSessionRecord:
        record = ConversationSession(
            id=uuid4(),
            user_id=user_id,
            title=title,
            status=ConversationSessionStatus.ACTIVE.value,
        )
        self._session.add(record)
        await self._commit_and_refresh(record)
        return _session_record(record)

    async def create_project_session(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
        title: str | None = None,
    ) -> ConversationSessionRecord:
        record = ConversationSession(
            id=uuid4(),
            user_id=user_id,
            title=title,
            organization_id=organization_id,
            project_id=project_id,
            status=ConversationSessionStatus.ACTIVE.value,
        )
        self._session.add(record)
        await self._commit_and_refresh(record)
        return _session_record(record)

    async def get_session(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
    ) -> ConversationSessionRecord | None:
        result = await self._session.execute(
            select(ConversationSession).where(
                ConversationSession.id == session_id,
                ConversationSession.user_id == user_id,
            ),
        )
        record = result.scalar_one_or_none()
        return _session_record(record) if record is not None else None

    async def get_session_with_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
    ) -> ConversationSessionRecord | None:
        result = await self._session.execute(
            select(ConversationSession)
            .options(
                selectinload(ConversationSession.messages).selectinload(
                    ConversationMessage.document_references
                )
            )
            .where(
                ConversationSession.id == session_id,
                ConversationSession.user_id == user_id,
            ),
        )
        record = result.scalar_one_or_none()
        return _session_record(record, include_messages=True) if record else None

    async def get_project_session_with_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
    ) -> ConversationSessionRecord | None:
        result = await self._session.execute(
            select(ConversationSession)
            .options(
                selectinload(ConversationSession.messages).selectinload(
                    ConversationMessage.document_references
                )
            )
            .where(
                ConversationSession.id == session_id,
                ConversationSession.user_id == user_id,
                ConversationSession.organization_id == organization_id,
                ConversationSession.project_id == project_id,
            ),
        )
        record = result.scalar_one_or_none()
        return _session_record(record, include_messages=True) if record else None

    async def list_sessions(
        self,
        *,
        user_id: UUID,
        limit: int,
    ) -> list[ConversationSessionRecord]:
        result = await self._session.execute(
            select(ConversationSession)
            .where(ConversationSession.user_id == user_id)
            .order_by(ConversationSession.updated_at.desc())
            .limit(limit),
        )
        return [_session_record(record) for record in result.scalars().all()]

    async def list_project_sessions(
        self,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
        limit: int,
    ) -> list[ConversationSessionRecord]:
        result = await self._session.execute(
            select(ConversationSession)
            .where(
                ConversationSession.user_id == user_id,
                ConversationSession.organization_id == organization_id,
                ConversationSession.project_id == project_id,
            )
            .order_by(ConversationSession.updated_at.desc())
            .limit(limit),
        )
        return [_session_record(record) for record in result.scalars().all()]

    async def append_message(
        self,
        message: ConversationMessageCreate,
        *,
        user_id: UUID,
    ) -> ConversationMessageRecord:
        session = await self._get_session_model(message.session_id, user_id=user_id)
        if session is None:
            msg = f"Conversation session not found: {message.session_id}"
            raise KeyError(msg)
        sequence = await self._next_sequence(message.session_id)
        record = ConversationMessage(
            id=uuid4(),
            session_id=message.session_id,
            workflow_id=message.workflow_id,
            role=message.role.value,
            sequence=sequence,
            content=message.content,
            status=message.status.value,
            error_message=message.error_message,
            citations=list(message.citations),
            sources=list(message.sources),
            message_metadata=message.metadata or {},
            document_references=[
                ConversationMessageDocument(
                    id=uuid4(),
                    document_id=reference.document_id,
                    file_metadata_id=reference.file_metadata_id,
                    reference_type=reference.reference_type,
                )
                for reference in message.document_references
            ],
        )
        self._session.add(record)
        session.updated_at = func.now()
        await self._commit_and_refresh(record)
        return await self._get_message_record(record.id, user_id=user_id)

    async def append_project_message(
        self,
        message: ConversationMessageCreate,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
    ) -> ConversationMessageRecord:
        session = await self._get_project_session_model(
            message.session_id,
            user_id=user_id,
            organization_id=organization_id,
            project_id=project_id,
        )
        if session is None:
            msg = f"Conversation session not found: {message.session_id}"
            raise KeyError(msg)
        sequence = await self._next_sequence(message.session_id)
        record = ConversationMessage(
            id=uuid4(),
            session_id=message.session_id,
            workflow_id=message.workflow_id,
            role=message.role.value,
            sequence=sequence,
            content=message.content,
            status=message.status.value,
            error_message=message.error_message,
            citations=list(message.citations),
            sources=list(message.sources),
            message_metadata=message.metadata or {},
            document_references=[
                ConversationMessageDocument(
                    id=uuid4(),
                    document_id=reference.document_id,
                    file_metadata_id=reference.file_metadata_id,
                    reference_type=reference.reference_type,
                )
                for reference in message.document_references
            ],
        )
        self._session.add(record)
        session.updated_at = func.now()
        await self._commit_and_refresh(record)
        return await self._get_project_message_record(
            record.id,
            user_id=user_id,
            organization_id=organization_id,
            project_id=project_id,
        )

    async def update_message_workflow(
        self,
        message_id: UUID,
        workflow_id: UUID | None,
        *,
        user_id: UUID,
    ) -> ConversationMessageRecord:
        record = await self._get_message_model(message_id, user_id=user_id)
        if record is None:
            msg = f"Conversation message not found: {message_id}"
            raise KeyError(msg)

        record.workflow_id = workflow_id
        await self._commit_and_refresh(record)
        return await self._get_message_record(record.id, user_id=user_id)

    async def update_project_message_workflow(
        self,
        message_id: UUID,
        workflow_id: UUID | None,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
    ) -> ConversationMessageRecord:
        record = await self._get_project_message_model(
            message_id,
            user_id=user_id,
            organization_id=organization_id,
            project_id=project_id,
        )
        if record is None:
            msg = f"Conversation message not found: {message_id}"
            raise KeyError(msg)

        record.workflow_id = workflow_id
        await self._commit_and_refresh(record)
        return await self._get_project_message_record(
            record.id,
            user_id=user_id,
            organization_id=organization_id,
            project_id=project_id,
        )

    async def recent_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
        limit: int,
    ) -> list[ConversationMessageRecord]:
        result = await self._session.execute(
            select(ConversationMessage)
            .options(selectinload(ConversationMessage.document_references))
            .join(ConversationSession)
            .where(ConversationMessage.session_id == session_id)
            .where(ConversationSession.user_id == user_id)
            .order_by(ConversationMessage.sequence.desc())
            .limit(limit),
        )
        records = [_message_record(message) for message in result.scalars().all()]
        return list(reversed(records))

    async def recent_project_messages(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
        limit: int,
    ) -> list[ConversationMessageRecord]:
        result = await self._session.execute(
            select(ConversationMessage)
            .options(selectinload(ConversationMessage.document_references))
            .join(ConversationSession)
            .where(
                ConversationMessage.session_id == session_id,
                ConversationSession.user_id == user_id,
                ConversationSession.organization_id == organization_id,
                ConversationSession.project_id == project_id,
            )
            .order_by(ConversationMessage.sequence.desc())
            .limit(limit),
        )
        records = [_message_record(message) for message in result.scalars().all()]
        return list(reversed(records))

    async def _next_sequence(self, session_id: UUID) -> int:
        result = await self._session.execute(
            select(func.max(ConversationMessage.sequence)).where(
                ConversationMessage.session_id == session_id
            ),
        )
        return int(result.scalar_one_or_none() or 0) + 1

    async def _get_message_model(
        self,
        message_id: UUID,
        *,
        user_id: UUID,
    ) -> ConversationMessage | None:
        result = await self._session.execute(
            select(ConversationMessage)
            .options(selectinload(ConversationMessage.document_references))
            .join(ConversationSession)
            .where(
                ConversationMessage.id == message_id,
                ConversationSession.user_id == user_id,
            ),
        )
        return result.scalar_one_or_none()

    async def _get_project_message_model(
        self,
        message_id: UUID,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
    ) -> ConversationMessage | None:
        result = await self._session.execute(
            select(ConversationMessage)
            .options(selectinload(ConversationMessage.document_references))
            .join(ConversationSession)
            .where(
                ConversationMessage.id == message_id,
                ConversationSession.user_id == user_id,
                ConversationSession.organization_id == organization_id,
                ConversationSession.project_id == project_id,
            ),
        )
        return result.scalar_one_or_none()

    async def _get_message_record(
        self,
        message_id: UUID,
        *,
        user_id: UUID,
    ) -> ConversationMessageRecord:
        record = await self._get_message_model(message_id, user_id=user_id)
        if record is None:
            msg = f"Conversation message not found: {message_id}"
            raise KeyError(msg)
        return _message_record(record)

    async def _get_project_message_record(
        self,
        message_id: UUID,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
    ) -> ConversationMessageRecord:
        record = await self._get_project_message_model(
            message_id,
            user_id=user_id,
            organization_id=organization_id,
            project_id=project_id,
        )
        if record is None:
            msg = f"Conversation message not found: {message_id}"
            raise KeyError(msg)
        return _message_record(record)

    async def _get_session_model(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
    ) -> ConversationSession | None:
        result = await self._session.execute(
            select(ConversationSession).where(
                ConversationSession.id == session_id,
                ConversationSession.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_project_session_model(
        self,
        session_id: UUID,
        *,
        user_id: UUID,
        organization_id: UUID,
        project_id: UUID,
    ) -> ConversationSession | None:
        result = await self._session.execute(
            select(ConversationSession).where(
                ConversationSession.id == session_id,
                ConversationSession.user_id == user_id,
                ConversationSession.organization_id == organization_id,
                ConversationSession.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()

    async def _commit_and_refresh(self, record: object) -> None:
        try:
            await self._session.flush()
            await self._session.refresh(record)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise


def _session_record(
    session: ConversationSession,
    *,
    include_messages: bool = False,
) -> ConversationSessionRecord:
    messages = ()
    if include_messages:
        messages = tuple(
            _message_record(message)
            for message in sorted(session.messages, key=lambda item: item.sequence)
        )
    return ConversationSessionRecord(
        user_id=session.user_id,
        id=session.id,
        title=session.title,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
        organization_id=session.organization_id,
        project_id=session.project_id,
        messages=messages,
    )


def _message_record(message: ConversationMessage) -> ConversationMessageRecord:
    return ConversationMessageRecord(
        id=message.id,
        session_id=message.session_id,
        role=message.role,
        sequence=message.sequence,
        content=message.content,
        workflow_id=message.workflow_id,
        status=message.status,
        error_message=message.error_message,
        citations=tuple(message.citations or ()),
        sources=tuple(message.sources or ()),
        metadata=message.message_metadata or {},
        document_references=tuple(
            _document_reference_record(reference)
            for reference in message.document_references
        ),
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


def _document_reference_record(
    reference: ConversationMessageDocument,
) -> ConversationDocumentReferenceRecord:
    return ConversationDocumentReferenceRecord(
        id=reference.id,
        message_id=reference.message_id,
        document_id=reference.document_id,
        file_metadata_id=reference.file_metadata_id,
        reference_type=reference.reference_type,
        created_at=reference.created_at,
    )
