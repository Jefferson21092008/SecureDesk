from alembic import op
import sqlalchemy as sa

revision = "0004_add_ticket_assignment"
down_revision = "0003_add_ticket_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("assigned_agent_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_tickets_assigned_agent_id_users",
        "tickets",
        "users",
        ["assigned_agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_tickets_assigned_agent_id",
        "tickets",
        ["assigned_agent_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tickets_assigned_agent_id", table_name="tickets")
    op.drop_constraint(
        "fk_tickets_assigned_agent_id_users",
        "tickets",
        type_="foreignkey",
    )
    op.drop_column("tickets", "assigned_agent_id")
