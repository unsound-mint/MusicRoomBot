"""Add location_prompted and absence_reported to bookings

Revision ID: 3be4cb49dc45
Revises: 85c36913b005
Create Date: 2025-11-28 13:42:35.074508

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3be4cb49dc45'
down_revision: Union[str, Sequence[str], None] = '85c36913b005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Only add columns if they don't exist
    conn = op.get_bind()

    # Check existing columns
    existing = conn.exec_driver_sql(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='bookings'"
    ).fetchall()
    existing_cols = {row[0] for row in existing}

    # Add location_prompted if missing
    if 'location_prompted' not in existing_cols:
        op.add_column(
            'bookings',
            sa.Column('location_prompted', sa.Boolean(), nullable=False, server_default="false")
        )

    # Add absence_reported if missing
    if 'absence_reported' not in existing_cols:
        op.add_column(
            'bookings',
            sa.Column('absence_reported', sa.Boolean(), nullable=False, server_default="false")
        )


def downgrade():
    op.drop_column('bookings', 'absence_reported')
    op.drop_column('bookings', 'location_prompted')