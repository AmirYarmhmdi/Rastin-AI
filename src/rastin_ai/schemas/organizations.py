"""Public API schemas for organization endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from rastin_ai.database.enums import OrganizationMemberRole


class OrganizationCreateRequest(BaseModel):
    """Request body for creating an organization."""

    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=120)


class OrganizationResponse(BaseModel):
    """Organization metadata visible to a member."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class OrganizationListResponse(BaseModel):
    """Response envelope for organizations."""

    organizations: list[OrganizationResponse]


class OrganizationMemberCreateRequest(BaseModel):
    """Request body for adding an existing user to an organization."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    role: OrganizationMemberRole = OrganizationMemberRole.MEMBER


class OrganizationMemberResponse(BaseModel):
    """Organization membership metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    role: str
    user_is_active: bool
    user_email: str | None = None
    user_display_name: str | None = None
    created_at: datetime
    updated_at: datetime


class OrganizationMemberListResponse(BaseModel):
    """Response envelope for organization members."""

    members: list[OrganizationMemberResponse]
