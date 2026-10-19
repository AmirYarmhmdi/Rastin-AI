"""Add project document scope.

Revision ID: 20260807_0008
Revises: 20260807_0007
Create Date: 2026-08-07 00:08:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260807_0008"
down_revision: str | Sequence[str] | None = "20260807_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _assert_existing_documents_are_legacy_compatible()

    op.create_unique_constraint(
        "uq_projects_id_organization_id",
        "projects",
        ["id", "organization_id"],
    )

    op.add_column(
        "sessions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "sessions",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_sessions_organization_id"),
        "sessions",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_sessions_project_id"),
        "sessions",
        ["project_id"],
    )
    op.create_index(
        "ix_sessions_organization_id_project_id",
        "sessions",
        ["organization_id", "project_id"],
    )
    op.create_check_constraint(
        op.f("ck_sessions_session_project_scope_pair"),
        "sessions",
        "(organization_id is null and project_id is null) or "
        "(organization_id is not null and project_id is not null)",
    )
    op.create_foreign_key(
        op.f("fk_sessions_organization_id_organizations"),
        "sessions",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_sessions_project_id_projects"),
        "sessions",
        "projects",
        ["project_id", "organization_id"],
        ["id", "organization_id"],
    )

    op.add_column(
        "documents",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "document_scope",
            sa.String(length=32),
            server_default="LEGACY",
            nullable=False,
        ),
    )
    op.alter_column(
        "documents",
        "session_id",
        existing_type=postgresql.UUID(),
        nullable=True,
    )
    op.create_index(
        op.f("ix_documents_organization_id"),
        "documents",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_documents_project_id"),
        "documents",
        ["project_id"],
    )
    op.create_index(
        "ix_documents_organization_id_project_id",
        "documents",
        ["organization_id", "project_id"],
    )
    op.create_index(
        "ix_documents_project_scope",
        "documents",
        ["organization_id", "project_id", "document_scope"],
    )
    op.create_check_constraint(
        op.f("ck_documents_document_scope"),
        "documents",
        "document_scope in ('LEGACY', 'PROJECT_LIBRARY', 'CHAT_ATTACHMENT')",
    )
    op.create_check_constraint(
        op.f("ck_documents_document_scope_ownership"),
        "documents",
        "("
        "document_scope = 'LEGACY' "
        "and session_id is not null "
        "and organization_id is null "
        "and project_id is null"
        ") or ("
        "document_scope = 'PROJECT_LIBRARY' "
        "and session_id is null "
        "and organization_id is not null "
        "and project_id is not null"
        ") or ("
        "document_scope = 'CHAT_ATTACHMENT' "
        "and session_id is not null "
        "and organization_id is not null "
        "and project_id is not null"
        ")",
    )
    op.create_foreign_key(
        op.f("fk_documents_organization_id_organizations"),
        "documents",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_documents_project_id_projects"),
        "documents",
        "projects",
        ["project_id", "organization_id"],
        ["id", "organization_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_documents_project_id_projects"),
        "documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_documents_organization_id_organizations"),
        "documents",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("ck_documents_document_scope_ownership"), "documents")
    op.drop_constraint(op.f("ck_documents_document_scope"), "documents")
    op.drop_index("ix_documents_project_scope", "documents")
    op.drop_index("ix_documents_organization_id_project_id", "documents")
    op.drop_index(op.f("ix_documents_project_id"), "documents")
    op.drop_index(op.f("ix_documents_organization_id"), "documents")
    op.alter_column(
        "documents",
        "session_id",
        existing_type=postgresql.UUID(),
        nullable=False,
    )
    op.drop_column("documents", "document_scope")
    op.drop_column("documents", "project_id")
    op.drop_column("documents", "organization_id")

    op.drop_constraint(
        op.f("fk_sessions_project_id_projects"),
        "sessions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_sessions_organization_id_organizations"),
        "sessions",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("ck_sessions_session_project_scope_pair"), "sessions")
    op.drop_index("ix_sessions_organization_id_project_id", "sessions")
    op.drop_index(op.f("ix_sessions_project_id"), "sessions")
    op.drop_index(op.f("ix_sessions_organization_id"), "sessions")
    op.drop_column("sessions", "project_id")
    op.drop_column("sessions", "organization_id")

    op.drop_constraint("uq_projects_id_organization_id", "projects")


def _assert_existing_documents_are_legacy_compatible() -> None:
    bind = op.get_bind()
    null_session_count = bind.execute(
        sa.text("select count(*) from documents where session_id is null")
    ).scalar_one()
    if null_session_count:
        msg = (
            "Cannot apply project document scope migration: existing documents "
            "with NULL session_id would violate LEGACY document assumptions."
        )
        raise RuntimeError(msg)
