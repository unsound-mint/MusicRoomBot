import asyncio

from app.bootstrap import seed_database


def main() -> None:
    asyncio.run(seed_database())


if __name__ == "__main__":
    main()
