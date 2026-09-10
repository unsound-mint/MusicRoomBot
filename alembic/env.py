# alembic/env.py
import sys
import os
import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import pool
from alembic import context

# ---------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------
# This makes sure "app.*" imports work even when Alembic runs
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)


# ---------------------------------------------------------
# Alembic config object
# ---------------------------------------------------------
config = context.config

# ---------------------------------------------------------
# Load DATABASE_URL from your Python config
# ---------------------------------------------------------
from app.core.config import require_database_url

config.set_main_option("sqlalchemy.url", require_database_url())


# ---------------------------------------------------------
# Logging config
# ---------------------------------------------------------
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------
# Import ALL models to ensure Alembic sees metadata
# ---------------------------------------------------------

# Your unified Base
from app.core.database import Base

# Models (import all so autogenerate works)
from app.models.user import User
from app.models.admin import Admin
from app.models.booking import Booking
from app.models.config_model import Config as ConfigModel
from app.models.weekly_slot import WeeklySlot
from app.models.club import Club, ClubLeader, ClubSlotCancellation
from app.models.swap_offer import SwapOffer
from app.models.gift_offer import GiftOffer
from app.models.equipment_request import EquipmentRequest
from app.models.equipment_request_range import EquipmentRequestRange

# Alembic uses this metadata for migrations
target_metadata = Base.metadata

# ---------------------------------------------------------
# Migration functions
# ---------------------------------------------------------

def run_migrations_offline():
    """Run migrations without a DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    """Run migrations with a DB connection using an async engine."""
    connectable = create_async_engine(
        require_database_url(),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online():
    """Run migrations in online mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
