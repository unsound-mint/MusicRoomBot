import asyncio

from app.bootstrap import seed_database
from app.core.config import LOG_LEVEL
from app.core.logging import configure_logging


def main() -> None:
    configure_logging(LOG_LEVEL)
    asyncio.run(seed_database())


if __name__ == "__main__":
    main()
