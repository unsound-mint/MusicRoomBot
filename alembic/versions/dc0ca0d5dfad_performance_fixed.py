"""performance_fixed

Revision ID: dc0ca0d5dfad
Revises: 0285d5928829
Create Date: 2025-11-30 02:40:11.616470

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc0ca0d5dfad'
down_revision: Union[str, Sequence[str], None] = '0285d5928829'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # ----------------------------------------
    # 1) Add UNIQUE constraint to weekly_slots
    # ----------------------------------------
    # Prevent duplicate (weekday, hour) club slots
    op.create_unique_constraint(
        "uq_weekly_weekday_hour",
        "weekly_slots",
        ["weekday", "hour"]
    )

    # ------------------------------------------------
    # 2) Add created_at column to swap_offers (nullable)
    # ------------------------------------------------
    # Nulls allowed for historical rows; new rows get NOW()
    op.add_column(
        "swap_offers",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
    )

    # -----------------------------------------------
    # 3) Add index to bookings(date, hour)
    # -----------------------------------------------
    # Massive performance improvement for scheduler
    op.create_index(
        "ix_bookings_date_hour",
        "bookings",
        ["date", "hour"],
        unique=False,
    )


def downgrade():
    # Reverse operations

    # 1) Drop weekly slot unique constraint
    op.drop_constraint(
        "uq_weekly_weekday_hour",
        "weekly_slots",
        type_="unique"
    )

    # 2) Drop created_at from swap_offers
    op.drop_column("swap_offers", "created_at")

    # 3) Drop bookings index
    op.drop_index("ix_bookings_date_hour", table_name="bookings")
