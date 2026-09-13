from alembic import op
import sqlalchemy as sa

revision = "0005_ticket_lifecycle"
down_revision = "0004_add_ticket_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Keeps any ticket that was already CLOSED before this migration consistent.
    op.execute(
        sa.text(
            "UPDATE tickets "
            "SET closed_at = CURRENT_TIMESTAMP "
            "WHERE status = 'CLOSED' AND closed_at IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("tickets", "closed_at")
