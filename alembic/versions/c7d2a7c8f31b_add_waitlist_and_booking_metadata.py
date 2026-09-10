"""add waitlist and booking metadata

Revision ID: c7d2a7c8f31b
Revises: 9f2d3a7c1c0a
Create Date: 2026-03-24

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7d2a7c8f31b"
down_revision: Union[str, Sequence[str], None] = "9f2d3a7c1c0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column(
            "booking_source",
            sa.String(length=32),
            nullable=False,
            server_default="manual",
        ),
    )
    op.add_column(
        "bookings",
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", "hour", name="uq_waitlist_user_slot"),
    )
    op.create_index(
        "ix_waitlist_entries_date_hour_created",
        "waitlist_entries",
        ["date", "hour", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_waitlist_entries_user_id",
        "waitlist_entries",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_waitlist_entries_user_id", table_name="waitlist_entries")
    op.drop_index(
        "ix_waitlist_entries_date_hour_created",
        table_name="waitlist_entries",
    )
    op.drop_table("waitlist_entries")
    op.drop_column("bookings", "assigned_at")
    op.drop_column("bookings", "booking_source")
