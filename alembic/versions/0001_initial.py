from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    user_role = postgresql.ENUM("USER", "AGENT", "ADMIN", name="userrole", create_type=False)
    ticket_status = postgresql.ENUM("OPEN", "IN_PROGRESS", "CLOSED", name="ticketstatus", create_type=False)
    ticket_priority = postgresql.ENUM("LOW", "MEDIUM", "HIGH", name="ticketpriority", create_type=False)

    user_role.create(bind, checkfirst=True)
    ticket_status.create(bind, checkfirst=True)
    ticket_priority.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", user_role, nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", ticket_status, nullable=False),
        sa.Column("priority", ticket_priority, nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
    )
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_priority", "tickets", ["priority"])
    op.create_index("ix_tickets_owner_id", "tickets", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_tickets_owner_id", table_name="tickets")
    op.drop_index("ix_tickets_priority", table_name="tickets")
    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_table("tickets")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    bind = op.get_bind()
    postgresql.ENUM("LOW", "MEDIUM", "HIGH", name="ticketpriority", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM("OPEN", "IN_PROGRESS", "CLOSED", name="ticketstatus", create_type=False).drop(bind, checkfirst=True)
    postgresql.ENUM("USER", "AGENT", "ADMIN", name="userrole", create_type=False).drop(bind, checkfirst=True)
