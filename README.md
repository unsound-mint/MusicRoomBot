# Music Room Bot

[![CI](https://github.com/denisandreyev/MusicRoomBot/actions/workflows/ci.yml/badge.svg)](https://github.com/denisandreyev/MusicRoomBot/actions/workflows/ci.yml)

Telegram bot for Music Room booking, attendance verification, reminders, swaps, and admin operations.

## What It Does

- Lets members book available practice-room slots and cancel their own bookings.
- Prevents double-booking with both application checks and database constraints.
- Supports consecutive booking chains with reminders sent only for the first slot.
- Verifies attendance with location-based check-ins and configurable late windows.
- Handles member swaps, gift offers, club slots, equipment requests, warning appeals,
  and admin moderation flows.
- Stores operational settings in the database so chat IDs, geo settings, limits,
  and topic IDs can be changed without redeploying.

## Engineering Highlights

This project is intended to be readable as a production-style async Python service:

- **Clear service boundary:** Telegram handlers stay thin; booking, reminder,
  attendance, config, and admin rules live in `app/services/`.
- **Async database stack:** SQLAlchemy 2.0 async sessions with PostgreSQL and
  Alembic migrations.
- **Data integrity:** unique constraints and migration coverage protect critical
  booking invariants.
- **Operational resilience:** runtime config caching, booking backpressure,
  healthcheck entry point, Docker packaging, and CI migration smoke tests.
- **Quality gates:** Ruff, mypy, unit tests, lockfile verification, Alembic heads,
  Postgres-backed migration test, and Docker build run in GitHub Actions.

## Architecture

```text
app/
  bot/          Telegram routers, keyboards, rendering helpers, and interaction flow
  core/         configuration, database engine/session setup, logging, limits
  models/       SQLAlchemy ORM models
  services/     booking, reminders, attendance, config, admin, and domain rules
alembic/        schema migrations
tests/          unit tests for services, handlers, keyboards, config, and migrations
```

Business rules should live in `app/services/`. Telegram handlers in
`app/bot/handlers/` should receive updates, call services, and render responses.

For a deeper walkthrough of the system design, see
[docs/architecture.md](docs/architecture.md).

## Documentation

- [Architecture](docs/architecture.md) - system layers, data flow, scheduler, and quality gates.
- [Configuration](docs/configuration.md) - environment variables, runtime config keys, and bootstrap values.
- [Deployment](docs/deployment.md) - Docker Compose, migration behavior, and production notes.
- [Demo](docs/demo.md) - sanitized example flows for members and admins.

## Demo

The bot is designed around short Telegram flows that keep booking actions fast
for members and review actions explicit for admins.

Example member flow:

```text
Member: /start
Bot: Shows the main menu with booking, schedule, rules, equipment, and profile actions.

Member: Book a slot
Bot: Shows available days and slots.

Member: Selects Tuesday 18:00
Bot: Confirms the booking, adds calendar action, and schedules reminders.

Member: Shares location during the booked slot
Bot: Verifies attendance if the member is inside the configured radius and before
     the late deadline.
```

Example admin flow:

```text
Admin: Opens admin panel
Bot: Shows configuration, users, bookings, equipment requests, and warning tools.

Admin: Changes late check-in window
Bot: Persists the runtime setting in the database without requiring a redeploy.
```

## Environment

Create `.env` from [`.env.example`](.env.example) and set the required values:

- `BOT_TOKEN`
- `DATABASE_URL` for local runs
- `TIMEZONE`
- `ACCESS_FORM_URL`
- `LOG_LEVEL` defaults to `INFO`; recognized values are `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`, and `NOTSET`
- Logs are emitted as newline-delimited JSON with stable `event` fields and custom `extra` fields.

Create your own Telegram bot token with BotFather. Do not commit `.env`,
database dumps, Telegram chat IDs, topic IDs, coordinates for a private room, or
private form links.

Runtime bot settings are stored in the `config` table and can be bootstrapped
with `BOOTSTRAP_CONFIG_<CONFIG_KEY>` environment variables. For a real
deployment, set at least these values before running `app.seed` or
`app.bootstrap`:

- `BOOTSTRAP_CONFIG_ADMIN_CHAT_ID`
- `BOOTSTRAP_CONFIG_MEMBER_CHAT_ID`
- `BOOTSTRAP_CONFIG_ACCESS_CHAT_ID`
- `BOOTSTRAP_CONFIG_GEO_CENTER_LAT`
- `BOOTSTRAP_CONFIG_GEO_CENTER_LON`

Optional topic settings:

- `BOOTSTRAP_CONFIG_MEMBER_TOPIC_ID`
- `EQUIPMENT_TOPIC_ID` or `BOOTSTRAP_CONFIG_EQUIPMENT_TOPIC_ID`

## Local Run

1. Install dependencies with `uv sync --frozen`.
2. Run migrations with `uv run python -m app.migrate`.
3. For first-time setup, seed default data with `uv run python -m app.seed`.
4. Start the bot with `uv run python -m app.bot.main`.

For development dependencies, use `uv sync --frozen --extra dev`.

## Dependency Locks

`uv.lock` is the resolver source of truth. The pip-compatible exports are:

- `requirements.lock` for runtime/container installs
- `requirements-dev.lock` for local development and CI

After changing dependencies in `pyproject.toml`, refresh the lock files:

```bash
uv lock
uv export --frozen --no-dev --no-emit-project --output-file requirements.lock
uv export --frozen --extra dev --no-emit-project --output-file requirements-dev.lock
```

## Docker Run

1. Create `.env` from `.env.example` and set `BOT_TOKEN`.
2. Build the image with `docker compose build`.
3. Start the bot and Postgres with `docker compose up -d`.

The bot container runs `app.migrate` on startup, which applies Alembic
migrations before polling starts. To seed default data for first-time setup, run
`docker compose run --rm bot python -m app.seed`.

The Compose setup runs one bot container and one Postgres container. Keep the
bot scaled to a single replica because polling and scheduled reminder jobs are
not distributed-safe.

The default Compose database credentials are for local development only. Set
strong `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` values before any
production deployment.

## Public Repository Checklist

Before publishing a fork or mirror:

- Run a secret scan across the full git history.
- Replace private chat IDs, topic IDs, geo coordinates, and form URLs with your
  own runtime config values.
- Rotate any bot token, database password, or invite link that was ever committed.
- Keep `.env` and database dumps out of git.

## Checks

- Install: `uv sync --frozen --extra dev`
- Lint: `uv run ruff check app tests`
- Types: `uv run mypy app`
- Tests: `uv run python -m unittest discover -s tests`
- Migrations: `uv run alembic heads`
- Migration smoke test: `uv run alembic upgrade head` against Postgres
- Docker build: `docker build -t musicroom:ci .`

CI runs these checks on push and pull requests with Python 3.13, verifies the
lockfile with `uv lock --locked`, applies migrations against Postgres, runs the
healthcheck, and builds the Docker image.
