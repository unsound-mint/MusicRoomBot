"""remove waitlist entries

Revision ID: 6f8e3c2d1a90
Revises: 10d036b22ff7
Create Date: 2026-05-18 00:00:00.000000

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "6f8e3c2d1a90"
down_revision: str | Sequence[str] | None = "10d036b22ff7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("waitlist_entries")


def downgrade() -> None:
    op.create_table(
        "waitlist_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("cancel_booking_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["cancel_booking_id"],
            ["bookings.id"],
            name="fk_waitlist_cancel_booking",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", "hour", name="uq_waitlist_user_slot"),
    )
    op.create_index(
        "ix_waitlist_entries_date_hour_created",
        "waitlist_entries",
        ["date", "hour", "created_at"],
    )
    op.create_index("ix_waitlist_entries_user_id", "waitlist_entries", ["user_id"])
