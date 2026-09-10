# app/core/database.py
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import (
    DB_MAX_OVERFLOW,
    DB_POOL_SIZE,
    DB_POOL_TIMEOUT,
    require_database_url,
)


class Base(DeclarativeBase):
    pass

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine

    if _engine is None:
        _engine = create_async_engine(
            require_database_url(),
            echo=False,
            future=True,
            pool_size=DB_POOL_SIZE,
            max_overflow=DB_MAX_OVERFLOW,
            pool_timeout=DB_POOL_TIMEOUT,
            pool_pre_ping=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker

    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker

    if _engine is None:
        return

    await _engine.dispose()
    _engine = None
    _sessionmaker = None


class _LazySessionFactory:
    def __call__(self, *args: Any, **kwargs: Any) -> AsyncSession:
        return get_sessionmaker()(*args, **kwargs)


AsyncSessionLocal = _LazySessionFactory()


# Dependency helper
async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
