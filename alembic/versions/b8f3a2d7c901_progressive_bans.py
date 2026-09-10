"""progressive bans

Revision ID: b8f3a2d7c901
Revises: a1c2d3e4f5b6
Create Date: 2026-05-19 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8f3a2d7c901"
down_revision: str | Sequence[str] | None = "a1c2d3e4f5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("ban_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("banned_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_banned_until", "users", ["banned_until"], unique=False)
    op.alter_column("users", "ban_count", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_users_banned_until", table_name="users")
    op.drop_column("users", "banned_until")
    op.drop_column("users", "ban_count")
