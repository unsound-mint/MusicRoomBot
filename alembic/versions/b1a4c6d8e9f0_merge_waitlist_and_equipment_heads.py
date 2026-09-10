"""merge waitlist and equipment heads

Revision ID: b1a4c6d8e9f0
Revises: c7d2a7c8f31b, 8f2d1a7c9b4e
Create Date: 2026-03-25 00:30:00.000000

"""

from typing import Sequence, Union


revision: str = "b1a4c6d8e9f0"
down_revision: Union[str, Sequence[str], None] = ("c7d2a7c8f31b", "8f2d1a7c9b4e")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
