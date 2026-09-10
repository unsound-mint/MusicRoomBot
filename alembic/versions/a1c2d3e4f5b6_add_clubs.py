"""add clubs

Revision ID: a1c2d3e4f5b6
Revises: 7b2d9a4c1e0f
Create Date: 2026-05-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1c2d3e4f5b6"
down_revision: str | Sequence[str] | None = "7b2d9a4c1e0f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clubs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_clubs_name", "clubs", ["name"], unique=False)

    op.add_column("weekly_slots", sa.Column("club_id", sa.Integer(), nullable=True))
    op.create_index("ix_weekly_slots_club_id", "weekly_slots", ["club_id"], unique=False)
    op.create_foreign_key(
        "fk_weekly_slots_club_id_clubs",
        "weekly_slots",
        "clubs",
        ["club_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "club_leaders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("club_id", "user_id", name="uq_club_leader_club_user"),
    )
    op.create_index("ix_club_leaders_user_id", "club_leaders", ["user_id"], unique=False)

    op.create_table(
        "club_slot_cancellations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), nullable=False),
        sa.Column("weekly_slot_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("cancelled_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["club_id"], ["clubs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["weekly_slot_id"], ["weekly_slots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "weekly_slot_id",
            "date",
            name="uq_club_slot_cancellation_slot_date",
        ),
    )
    op.create_index(
        "ix_club_slot_cancellations_date",
        "club_slot_cancellations",
        ["date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_club_slot_cancellations_date", table_name="club_slot_cancellations")
    op.drop_table("club_slot_cancellations")
    op.drop_index("ix_club_leaders_user_id", table_name="club_leaders")
    op.drop_table("club_leaders")
    op.drop_constraint("fk_weekly_slots_club_id_clubs", "weekly_slots", type_="foreignkey")
    op.drop_index("ix_weekly_slots_club_id", table_name="weekly_slots")
    op.drop_column("weekly_slots", "club_id")
    op.drop_index("ix_clubs_name", table_name="clubs")
    op.drop_table("clubs")
