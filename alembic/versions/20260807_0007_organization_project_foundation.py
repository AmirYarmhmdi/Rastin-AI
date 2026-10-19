"""Add organization and project foundation.

Revision ID: 20260807_0007
Revises: 20260807_0006
Create Date: 2026-08-07 00:07:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260807_0007"
down_revision: str | Sequence[str] | None = "20260807_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_organizations_created_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("slug", name=op.f("uq_organizations_slug")),
    )
    op.create_index(
        op.f("ix_organizations_created_by_user_id"),
        "organizations",
        ["created_by_user_id"],
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"])

    op.create_table(
        "organization_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.String(length=32),
            server_default="MEMBER",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role in ('OWNER', 'MEMBER')",
            name=op.f("ck_organization_members_organization_member_role"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_members_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_organization_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_members")),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_members_organization_id_user_id",
        ),
    )
    op.create_index(
        op.f("ix_organization_members_organization_id"),
        "organization_members",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_organization_members_user_id"),
        "organization_members",
        ["user_id"],
    )

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_projects_created_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_projects_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(
        op.f("ix_projects_created_by_user_id"),
        "projects",
        ["created_by_user_id"],
    )
    op.create_index(
        op.f("ix_projects_organization_id"),
        "projects",
        ["organization_id"],
    )

    op.create_table(
        "project_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.String(length=32),
            server_default="MEMBER",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role in ('ADMIN', 'MEMBER', 'VIEWER')",
            name=op.f("ck_project_members_project_member_role"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_members_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_project_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_members")),
        sa.UniqueConstraint(
            "project_id",
            "user_id",
            name="uq_project_members_project_id_user_id",
        ),
    )
    op.create_index(
        op.f("ix_project_members_project_id"),
        "project_members",
        ["project_id"],
    )
    op.create_index(
        op.f("ix_project_members_user_id"),
        "project_members",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_project_members_user_id"), "project_members")
    op.drop_index(op.f("ix_project_members_project_id"), "project_members")
    op.drop_table("project_members")
    op.drop_index(op.f("ix_projects_organization_id"), "projects")
    op.drop_index(op.f("ix_projects_created_by_user_id"), "projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_organization_members_user_id"), "organization_members")
    op.drop_index(
        op.f("ix_organization_members_organization_id"),
        "organization_members",
    )
    op.drop_table("organization_members")
    op.drop_index(op.f("ix_organizations_slug"), "organizations")
    op.drop_index(op.f("ix_organizations_created_by_user_id"), "organizations")
    op.drop_table("organizations")
