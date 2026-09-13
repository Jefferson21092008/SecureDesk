from alembic import op
import sqlalchemy as sa

revision = "0003_add_ticket_history"
down_revision = "0002_add_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticket_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.Integer(),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_ticket_history_ticket_id", "ticket_history", ["ticket_id"])
    op.create_index("ix_ticket_history_actor_id", "ticket_history", ["actor_id"])
    op.create_index("ix_ticket_history_action", "ticket_history", ["action"])


def downgrade() -> None:
    op.drop_index("ix_ticket_history_action", table_name="ticket_history")
    op.drop_index("ix_ticket_history_actor_id", table_name="ticket_history")
    op.drop_index("ix_ticket_history_ticket_id", table_name="ticket_history")
    op.drop_table("ticket_history")
