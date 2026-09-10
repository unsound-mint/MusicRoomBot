"""placeholder for removed equipment request needed_at migration

Revision ID: f2d7d4a1c8b1
Revises: b1a4c6d8e9f0
Create Date: 2026-03-25 00:00:01.000000

"""

from collections.abc import Sequence

revision: str = "f2d7d4a1c8b1"
down_revision: str | Sequence[str] | None = "b1a4c6d8e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
