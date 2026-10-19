"""Add project chat workflow scope.

Revision ID: 20260807_0009
Revises: 20260807_0008
Create Date: 2026-08-07 00:09:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260807_0009"
down_revision: str | Sequence[str] | None = "20260807_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_sessions_project_user_updated_at",
        "sessions",
        ["organization_id", "project_id", "user_id", "updated_at"],
    )
    op.create_unique_constraint(
        "uq_sessions_id_organization_id_project_id",
        "sessions",
        ["id", "organization_id", "project_id"],
    )

    op.add_column(
        "workflow_executions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "workflow_executions",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_workflow_executions_organization_id"),
        "workflow_executions",
        ["organization_id"],
    )
    op.create_index(
        op.f("ix_workflow_executions_project_id"),
        "workflow_executions",
        ["project_id"],
    )
    op.create_index(
        "ix_workflow_executions_organization_id_project_id",
        "workflow_executions",
        ["organization_id", "project_id"],
    )
    op.create_index(
        "ix_workflow_executions_project_session_user",
        "workflow_executions",
        ["organization_id", "project_id", "session_id", "user_id"],
    )
    op.create_check_constraint(
        op.f("ck_workflow_executions_workflow_execution_project_scope_pair"),
        "workflow_executions",
        "(organization_id is null and project_id is null) or "
        "(organization_id is not null and project_id is not null)",
    )
    op.create_foreign_key(
        op.f("fk_workflow_executions_organization_id_organizations"),
        "workflow_executions",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_workflow_executions_project_id_projects"),
        "workflow_executions",
        "projects",
        ["project_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.create_foreign_key(
        "fk_workflow_executions_session_project_scope",
        "workflow_executions",
        "sessions",
        ["session_id", "organization_id", "project_id"],
        ["id", "organization_id", "project_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_workflow_executions_session_project_scope",
        "workflow_executions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_workflow_executions_project_id_projects"),
        "workflow_executions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_workflow_executions_organization_id_organizations"),
        "workflow_executions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_workflow_executions_workflow_execution_project_scope_pair"),
        "workflow_executions",
    )
    op.drop_index("ix_workflow_executions_project_session_user", "workflow_executions")
    op.drop_index(
        "ix_workflow_executions_organization_id_project_id",
        "workflow_executions",
    )
    op.drop_index(op.f("ix_workflow_executions_project_id"), "workflow_executions")
    op.drop_index(
        op.f("ix_workflow_executions_organization_id"),
        "workflow_executions",
    )
    op.drop_column("workflow_executions", "project_id")
    op.drop_column("workflow_executions", "organization_id")

    op.drop_constraint("uq_sessions_id_organization_id_project_id", "sessions")
    op.drop_index("ix_sessions_project_user_updated_at", "sessions")
