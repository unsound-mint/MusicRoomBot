"""add_waitlist_swap

Revision ID: 15a4e7bebcb7
Revises: f74f1e2a9c61
Create Date: 2026-03-26 15:01:18.346888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '15a4e7bebcb7'
down_revision: Union[str, Sequence[str], None] = 'f74f1e2a9c61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('waitlist_entries', sa.Column('cancel_booking_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_waitlist_cancel_booking', 
        'waitlist_entries', 'bookings', 
        ['cancel_booking_id'], ['id'], 
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_waitlist_cancel_booking', 'waitlist_entries', type_='foreignkey')
    op.drop_column('waitlist_entries', 'cancel_booking_id')
