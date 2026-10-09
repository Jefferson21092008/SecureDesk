"""Track per-attachment storage backend to preserve legacy local downloads.

Revision ID: 0014_attachment_storage_backend
Revises: 0013_add_user_invitations
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_attachment_storage_backend"
down_revision = "0013_add_user_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("storage_backend", sa.String(length=16), server_default="local", nullable=False),
    )


def downgrade() -> None:
    # Never silently reinterpret cloud objects as local files on rollback.
    non_local_exists = op.get_bind().execute(
        sa.text("SELECT 1 FROM attachments WHERE storage_backend <> 'local' LIMIT 1")
    ).scalar()
    if non_local_exists:
        raise RuntimeError("Cannot downgrade while non-local attachments are registered")
    op.drop_column("attachments", "storage_backend")
