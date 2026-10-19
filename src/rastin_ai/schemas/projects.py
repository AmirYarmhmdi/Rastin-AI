"""Public API schemas for project endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from rastin_ai.database.enums import ProjectMemberRole


class ProjectCreateRequest(BaseModel):
    """Request body for creating a project."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ProjectResponse(BaseModel):
    """Project metadata and current user's effective access."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    description: str | None = None
    created_by_user_id: UUID
    effective_role: str
    permissions: list[str]
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    """Response envelope for accessible projects."""

    projects: list[ProjectResponse]


class ProjectMemberCreateRequest(BaseModel):
    """Request body for adding an organization member to a project."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    role: ProjectMemberRole


class ProjectMemberResponse(BaseModel):
    """Project membership metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    user_id: UUID
    role: str
    user_is_active: bool
    user_email: str | None = None
    user_display_name: str | None = None
    created_at: datetime
    updated_at: datetime


class ProjectMemberListResponse(BaseModel):
    """Response envelope for project members."""

    members: list[ProjectMemberResponse]
