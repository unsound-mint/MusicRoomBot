from app.bootstrap import run_migrations
from app.core.config import LOG_LEVEL
from app.core.logging import configure_logging


def main() -> None:
    configure_logging(LOG_LEVEL)
    run_migrations()


if __name__ == "__main__":
    main()
