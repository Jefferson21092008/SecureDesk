"""add ticket attachments

Revision ID: 0008_add_ticket_attachments
Revises: 0007_add_ticket_categories
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_add_ticket_attachments"
down_revision: str | None = "0007_add_ticket_categories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("uploader_id", sa.Integer(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(op.f("ix_attachments_ticket_id"), "attachments", ["ticket_id"], unique=False)
    op.create_index(op.f("ix_attachments_uploader_id"), "attachments", ["uploader_id"], unique=False)
    op.create_index(op.f("ix_attachments_created_at"), "attachments", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_attachments_created_at"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_uploader_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_ticket_id"), table_name="attachments")
    op.drop_table("attachments")
