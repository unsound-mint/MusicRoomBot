"""allow admin weekly cancellations

Revision ID: e7b9c2d4a6f1
Revises: c4d9f9a31b20
Create Date: 2026-05-22 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e7b9c2d4a6f1"
down_revision: str | Sequence[str] | None = "c4d9f9a31b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "club_slot_cancellations",
        "club_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "club_slot_cancellations",
        "club_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
