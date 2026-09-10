"""make tg_user_id nullable

Revision ID: de4fa0947d3a
Revises: 3be4cb49dc45
Create Date: 2025-11-28 20:12:50.953299

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de4fa0947d3a'
down_revision: Union[str, Sequence[str], None] = '3be4cb49dc45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Make tg_user_id nullable
    op.alter_column(
        'users',
        'tg_user_id',
        existing_type=sa.BigInteger(),
        nullable=True
    )


def downgrade():
    # WARNING: this will fail if any tg_user_id is NULL at downgrade time
    op.alter_column(
        'users',
        'tg_user_id',
        existing_type=sa.BigInteger(),
        nullable=False
    )