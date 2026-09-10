"""add equipment request ranges

Revision ID: f74f1e2a9c61
Revises: b1a4c6d8e9f0
Create Date: 2026-03-25 00:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f74f1e2a9c61"
down_revision: str | Sequence[str] | None = "f2d7d4a1c8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "equipment_request_ranges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_request_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["equipment_request_id"],
            ["equipment_requests.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_equipment_request_ranges_request_id",
        "equipment_request_ranges",
        ["equipment_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_equipment_request_ranges_start_at",
        "equipment_request_ranges",
        ["start_at"],
        unique=False,
    )
    op.create_index(
        "ix_equipment_request_ranges_end_at",
        "equipment_request_ranges",
        ["end_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_equipment_request_ranges_end_at", table_name="equipment_request_ranges")
    op.drop_index("ix_equipment_request_ranges_start_at", table_name="equipment_request_ranges")
    op.drop_index("ix_equipment_request_ranges_request_id", table_name="equipment_request_ranges")
    op.drop_table("equipment_request_ranges")
