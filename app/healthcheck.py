import asyncio

from sqlalchemy import text

from app.core.config import require_bot_token
from app.core.database import dispose_engine, get_engine


async def _check() -> None:
    require_bot_token()
    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("select 1"))
    finally:
        await dispose_engine()


def main() -> None:
    asyncio.run(_check())


if __name__ == "__main__":
    main()
