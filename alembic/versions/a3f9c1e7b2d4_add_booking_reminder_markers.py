"""add booking reminder markers

Revision ID: a3f9c1e7b2d4
Revises: e7b9c2d4a6f1
Create Date: 2026-10-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3f9c1e7b2d4"
down_revision: str | Sequence[str] | None = "e7b9c2d4a6f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("reminded_hourly_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("reminded_15_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bookings", "reminded_15_at")
    op.drop_column("bookings", "reminded_hourly_at")
