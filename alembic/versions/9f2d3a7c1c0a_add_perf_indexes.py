"""add perf indexes

Revision ID: 9f2d3a7c1c0a
Revises: 3cce9839893f
Create Date: 2026-02-09

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9f2d3a7c1c0a"
down_revision: Union[str, Sequence[str], None] = "3cce9839893f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # User lookups by username are common in admin and start flows.
    op.create_index("ix_users_tg_username", "users", ["tg_username"], unique=False)

    # Booking queries often filter by user_id + date range (weekly counts, user bookings).
    op.create_index(
        "ix_bookings_user_id_date",
        "bookings",
        ["user_id", "date"],
        unique=False,
    )

    # Fast deletes/lookups for attendance logs.
    op.create_index(
        "ix_attendance_log_booking_id",
        "attendance_log",
        ["booking_id"],
        unique=False,
    )
    op.create_index(
        "ix_attendance_log_user_id",
        "attendance_log",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_attendance_log_user_id", table_name="attendance_log")
    op.drop_index("ix_attendance_log_booking_id", table_name="attendance_log")
    op.drop_index("ix_bookings_user_id_date", table_name="bookings")
    op.drop_index("ix_users_tg_username", table_name="users")

