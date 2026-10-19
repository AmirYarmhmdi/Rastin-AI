"""File guide.

- Use: Stores and reads uploaded file metadata through a repository boundary.
- Usage: Import FileMetadataCreate, FileMetadataRecord, FileMetadataRepository, and
  1 more from rastin_ai.repositories.file_metadata.
- Duties: Defines FileMetadataCreate, FileMetadataRecord, FileMetadataRepository,
  and SQLAlchemyFileMetadataRepository and related helper logic.
- Depends on: Project modules: rastin_ai.database.enums, and
  rastin_ai.database.models.file_metadata.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rastin_ai.database.enums import FileStorageStatus
from rastin_ai.database.models.file_metadata import FileMetadata


@dataclass(frozen=True)
class FileMetadataCreate:
    id: UUID
    original_filename: str
    storage_key: str
    storage_backend: str
    content_type: str | None
    normalized_extension: str
    size_bytes: int
    status: FileStorageStatus = FileStorageStatus.STORED
    document_id: UUID | None = None
    checksum_sha256: str | None = None


@dataclass(frozen=True)
class FileMetadataRecord:
    id: UUID
    original_filename: str
    storage_key: str
    storage_backend: str
    content_type: str | None
    normalized_extension: str
    size_bytes: int
    status: str
    created_at: datetime
    updated_at: datetime
    document_id: UUID | None = None
    checksum_sha256: str | None = None


class FileMetadataRepository(Protocol):
    async def create(self, metadata: FileMetadataCreate) -> FileMetadataRecord:
        """Persist a file metadata record."""

    async def get_by_id(self, file_id: UUID) -> FileMetadataRecord | None:
        """Return a file metadata record by ID."""

    async def list(self) -> list[FileMetadataRecord]:
        """Return uploaded file metadata records known to the application."""


class SQLAlchemyFileMetadataRepository:
    """SQLAlchemy-backed repository for file metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, metadata: FileMetadataCreate) -> FileMetadataRecord:
        record = FileMetadata(
            id=metadata.id,
            document_id=metadata.document_id,
            original_filename=metadata.original_filename,
            storage_key=metadata.storage_key,
            storage_backend=metadata.storage_backend,
            content_type=metadata.content_type,
            normalized_extension=metadata.normalized_extension,
            size_bytes=metadata.size_bytes,
            status=metadata.status.value,
            checksum_sha256=metadata.checksum_sha256,
        )
        self._session.add(record)

        try:
            await self._session.flush()
            await self._session.refresh(record)
            created_record = _to_record(record)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return created_record

    async def get_by_id(self, file_id: UUID) -> FileMetadataRecord | None:
        result = await self._session.execute(
            select(FileMetadata).where(FileMetadata.id == file_id),
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None

        return _to_record(record)

    async def list(self) -> list[FileMetadataRecord]:
        result = await self._session.execute(
            select(FileMetadata).order_by(FileMetadata.created_at.desc()),
        )
        return [_to_record(record) for record in result.scalars().all()]


def _to_record(metadata: FileMetadata) -> FileMetadataRecord:
    return FileMetadataRecord(
        id=metadata.id,
        document_id=metadata.document_id,
        original_filename=metadata.original_filename,
        storage_key=metadata.storage_key,
        storage_backend=metadata.storage_backend,
        content_type=metadata.content_type,
        normalized_extension=metadata.normalized_extension,
        size_bytes=metadata.size_bytes,
        status=metadata.status,
        checksum_sha256=metadata.checksum_sha256,
        created_at=metadata.created_at,
        updated_at=metadata.updated_at,
    )
