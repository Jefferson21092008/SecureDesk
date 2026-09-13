from alembic import op
import sqlalchemy as sa

revision = "0007_add_ticket_categories"
down_revision = "0006_add_ticket_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_categories_name", "categories", ["name"], unique=True)

    op.add_column("tickets", sa.Column("category_id", sa.Integer(), nullable=True))
    op.create_index("ix_tickets_category_id", "tickets", ["category_id"])
    op.create_foreign_key(
        "fk_tickets_category_id_categories",
        "tickets",
        "categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tickets_category_id_categories", "tickets", type_="foreignkey")
    op.drop_index("ix_tickets_category_id", table_name="tickets")
    op.drop_column("tickets", "category_id")
    op.drop_index("ix_categories_name", table_name="categories")
    op.drop_table("categories")
