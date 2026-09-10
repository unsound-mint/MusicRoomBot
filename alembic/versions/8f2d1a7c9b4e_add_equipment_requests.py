"""add equipment requests

Revision ID: 8f2d1a7c9b4e
Revises: 30a1037709de
Create Date: 2026-03-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f2d1a7c9b4e"
down_revision: Union[str, Sequence[str], None] = "30a1037709de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "equipment_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requester_tg_user_id", sa.BigInteger(), nullable=False),
        sa.Column("requester_username", sa.String(), nullable=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("club_name", sa.String(), nullable=False),
        sa.Column("event_name", sa.String(), nullable=False),
        sa.Column("venue", sa.String(), nullable=False),
        sa.Column("equipment_text", sa.Text(), nullable=False),
        sa.Column("needed_at_text", sa.Text(), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'submitted'"),
        ),
        sa.Column("admin_tg_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("review_message_id", sa.Integer(), nullable=True),
        sa.Column(
            "requester_dm_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "equipment_post_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("requester_dm_error", sa.Text(), nullable=True),
        sa.Column("equipment_post_error", sa.Text(), nullable=True),
    )

    op.create_index(
        "ix_equipment_requests_status",
        "equipment_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_equipment_requests_requester_tg_user_id",
        "equipment_requests",
        ["requester_tg_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_equipment_requests_review_chat_message",
        "equipment_requests",
        ["review_chat_id", "review_message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_equipment_requests_review_chat_message",
        table_name="equipment_requests",
    )
    op.drop_index(
        "ix_equipment_requests_requester_tg_user_id",
        table_name="equipment_requests",
    )
    op.drop_index("ix_equipment_requests_status", table_name="equipment_requests")
    op.drop_table("equipment_requests")
