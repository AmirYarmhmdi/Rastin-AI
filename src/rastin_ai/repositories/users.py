"""Repository for authenticated application users."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rastin_ai.database.models.user import User
from rastin_ai.security.auth import ExternalIdentity


@dataclass(frozen=True)
class UserRecord:
    id: UUID
    issuer: str
    external_subject: str
    email: str | None
    display_name: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserRepository(Protocol):
    async def resolve_external_identity(
        self,
        identity: ExternalIdentity,
    ) -> UserRecord:
        """Return or create the local user mapped to an external identity."""

    async def get_by_id(self, user_id: UUID) -> UserRecord | None:
        """Return a user by local ID."""


class SQLAlchemyUserRepository:
    """SQLAlchemy-backed repository for users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_external_identity(
        self,
        identity: ExternalIdentity,
    ) -> UserRecord:
        result = await self._session.execute(
            select(User).where(
                User.issuer == identity.issuer,
                User.external_subject == identity.subject,
            )
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                issuer=identity.issuer,
                external_subject=identity.subject,
                email=identity.email,
                display_name=identity.display_name,
            )
            self._session.add(user)
        else:
            user.email = identity.email
            user.display_name = identity.display_name

        try:
            await self._session.flush()
            await self._session.refresh(user)
            record = _to_record(user)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return record

    async def get_by_id(self, user_id: UUID) -> UserRecord | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return _to_record(user) if user is not None else None


def _to_record(user: User) -> UserRecord:
    return UserRecord(
        id=user.id,
        issuer=user.issuer or "",
        external_subject=user.external_subject or "",
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
