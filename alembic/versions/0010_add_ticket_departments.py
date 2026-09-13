"""add ticket departments

Revision ID: 0010_add_ticket_departments
Revises: 0009_add_ticket_sla
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_add_ticket_departments"
down_revision: str | None = "0009_add_ticket_sla"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_departments_name", "departments", ["name"], unique=True)

    op.add_column("tickets", sa.Column("department_id", sa.Integer(), nullable=True))
    op.create_index("ix_tickets_department_id", "tickets", ["department_id"], unique=False)
    op.create_foreign_key(
        "fk_tickets_department_id_departments",
        "tickets",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tickets_department_id_departments", "tickets", type_="foreignkey")
    op.drop_index("ix_tickets_department_id", table_name="tickets")
    op.drop_column("tickets", "department_id")
    op.drop_index("ix_departments_name", table_name="departments")
    op.drop_table("departments")
