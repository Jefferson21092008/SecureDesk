"""add ticket SLA deadline

Revision ID: 0009_add_ticket_sla
Revises: 0008_add_ticket_attachments
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_add_ticket_sla"
down_revision: str | None = "0008_add_ticket_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Existing tickets receive the baseline resolution target measured from created_at.
    op.execute(
        sa.text(
            """
            UPDATE tickets
            SET sla_due_at = created_at + CASE
                WHEN priority = 'HIGH' THEN INTERVAL '4 hours'
                WHEN priority = 'MEDIUM' THEN INTERVAL '8 hours'
                ELSE INTERVAL '24 hours'
            END
            """
        )
    )

    op.alter_column(
        "tickets",
        "sla_due_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.create_index("ix_tickets_sla_due_at", "tickets", ["sla_due_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tickets_sla_due_at", table_name="tickets")
    op.drop_column("tickets", "sla_due_at")
