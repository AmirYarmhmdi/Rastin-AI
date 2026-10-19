"""Public API schemas for project-library documents."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectDocumentResponse(BaseModel):
    """Project-library document response."""

    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    file_metadata_id: UUID
    organization_id: UUID
    project_id: UUID
    uploaded_by_user_id: UUID | None = None
    filename: str
    content_type: str | None = None
    normalized_extension: str
    size_bytes: int
    checksum_sha256: str
    document_scope: str
    session_id: UUID | None = None
    status: str
    indexing_error_code: str | None = None
    indexing_error_message: str | None = None
    file_storage_status: str
    created_at: datetime
    updated_at: datetime


class ProjectDocumentListResponse(BaseModel):
    """Response envelope for project-library documents."""

    documents: list[ProjectDocumentResponse]
