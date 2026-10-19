"""File guide.

- Use: Defines public API schemas for document endpoints.
- Usage: Import document response models from rastin_ai.schemas.documents.
- Duties: Keeps API document schemas separate from database models.
- Depends on: External packages only: datetime, pydantic, and uuid.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DocumentUploadResponse(BaseModel):
    """Response returned after accepting a document upload."""

    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    filename: str
    content_type: str | None = None
    status: str
    workflow_id: UUID | None = None
    file_metadata_id: UUID | None = None
    normalized_extension: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    file_storage_status: str | None = None
    indexing_error_code: str | None = None
    indexing_error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentListItem(BaseModel):
    """Document summary returned from the list documents endpoint."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    content_type: str | None = None
    status: str
    created_at: datetime
    file_metadata_id: UUID | None = None
    normalized_extension: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    file_storage_status: str | None = None
    indexing_error_code: str | None = None
    indexing_error_message: str | None = None
    updated_at: datetime | None = None


class DocumentListResponse(BaseModel):
    """Response envelope for known documents."""

    documents: list[DocumentListItem]
