"""add gift offers

Revision ID: c4d9f9a31b20
Revises: b8f3a2d7c901
Create Date: 2026-05-19 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d9f9a31b20"
down_revision: Union[str, Sequence[str], None] = "b8f3a2d7c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gift_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("giver_user_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["giver_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gift_offers_booking_id", "gift_offers", ["booking_id"])
    op.create_index("ix_gift_offers_giver_user_id", "gift_offers", ["giver_user_id"])
    op.create_index(
        "ix_gift_offers_recipient_user_id", "gift_offers", ["recipient_user_id"]
    )
    op.create_index("ix_gift_offers_status", "gift_offers", ["status"])


def downgrade() -> None:
    op.drop_index("ix_gift_offers_status", table_name="gift_offers")
    op.drop_index("ix_gift_offers_recipient_user_id", table_name="gift_offers")
    op.drop_index("ix_gift_offers_giver_user_id", table_name="gift_offers")
    op.drop_index("ix_gift_offers_booking_id", table_name="gift_offers")
    op.drop_table("gift_offers")
