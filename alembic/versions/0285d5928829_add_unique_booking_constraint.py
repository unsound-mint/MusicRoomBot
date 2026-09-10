"""add unique booking constraint

Revision ID: 0285d5928829
Revises: de4fa0947d3a
Create Date: 2025-11-29 00:04:48.481851

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0285d5928829'
down_revision: Union[str, Sequence[str], None] = 'de4fa0947d3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_unique_constraint(
        "uq_booking_date_hour",
        "bookings",
        ["date", "hour"]
    )

def downgrade():
    op.drop_constraint("uq_booking_date_hour", "bookings", type_="unique")