"""add security audit logs

Revision ID: 0012_add_security_audit_logs
Revises: 0011_add_revoked_tokens
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_add_security_audit_logs"
down_revision: str | None = "0011_add_revoked_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_audit_logs_event_type", "security_audit_logs", ["event_type"], unique=False)
    op.create_index("ix_security_audit_logs_actor_id", "security_audit_logs", ["actor_id"], unique=False)
    op.create_index("ix_security_audit_logs_status_code", "security_audit_logs", ["status_code"], unique=False)
    op.create_index("ix_security_audit_logs_created_at", "security_audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_security_audit_logs_created_at", table_name="security_audit_logs")
    op.drop_index("ix_security_audit_logs_status_code", table_name="security_audit_logs")
    op.drop_index("ix_security_audit_logs_actor_id", table_name="security_audit_logs")
    op.drop_index("ix_security_audit_logs_event_type", table_name="security_audit_logs")
    op.drop_table("security_audit_logs")
