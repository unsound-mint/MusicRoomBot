# Architecture

Music Room Bot is an async Telegram booking service for a shared music practice
room. The code is organized so Telegram-specific interaction code is separate
from business rules, persistence, and operational concerns.

## System Overview

```text
Telegram users
    |
    v
aiogram Dispatcher
    |
    v
app/bot/handlers/
    |
    v
app/services/
    |
    v
SQLAlchemy async session
    |
    v
PostgreSQL
```

APScheduler runs background jobs for weekly resets, reminders, and attendance
checks. The bot runs as a single polling process because FSM storage, the
flash-book store and the rate limiter are in memory (see `docs/deployment.md`).

## Layers

### Bot Layer

`app/bot/` contains Telegram-facing code:

- `handlers/` receive Telegram updates and callbacks.
- `keyboards/` builds reply and inline keyboards.
- renderer/message helper modules keep Markdown and UI text consistent.

Handlers should stay thin. They validate the Telegram interaction state, call a
service, and render the result.

### Service Layer

`app/services/` owns business rules:

- `booking_service.py` manages slot availability, booking creation,
  cancellation, and reset behavior.
- `reminder_service.py` finds upcoming bookings and sends reminders only for the
  first slot in a consecutive chain.
- `geo_service.py` and `attendance_service.py` handle location verification and
  attendance state.
- `config_runtime.py` reads runtime settings through a short-lived cache.
- admin, equipment, club, warning, invite, and schedule services isolate the
  rest of the domain logic.

This boundary makes business behavior testable without a live Telegram bot.

### Data Layer

`app/models/` contains SQLAlchemy ORM models. Alembic migrations in `alembic/`
describe schema changes. Critical booking invariants are enforced at the
database level with unique constraints, not only with application checks.

The app uses SQLAlchemy 2.0-style async sessions and PostgreSQL via `asyncpg`.
Transaction ownership conventions are documented in
[transaction-conventions.md](transaction-conventions.md): handlers delegate
state changes to command services, query services never commit, and command
services own the commit for one business operation.

### Core Layer

`app/core/` contains cross-cutting infrastructure:

- `config.py` loads environment settings and supports `*_FILE` secret fallback.
- `database.py` owns the async engine and session factory.
- `limits.py` applies booking-flow backpressure.
- `logging.py` configures newline-delimited JSON application logging.
- `metrics.py` stores lightweight in-process counters and timings for admin
  status and local diagnostics.
- `rate_limit.py` and `reset_gate.py` provide operational controls.

## Runtime Configuration

Environment variables provide deployment-level settings such as `BOT_TOKEN`,
`DATABASE_URL`, `TIMEZONE`, pool tuning, and cache TTLs.

Bot-operational values such as admin chat IDs, member chat IDs, topic IDs, geo
center, and booking limits live in the database-backed runtime config table.
This allows admins to change operational settings without rebuilding or
redeploying the service.

## Booking Integrity

Booking creation uses service-level availability checks for user experience and
database-level uniqueness for correctness under concurrency. This keeps the
system safe if two users try to book the same slot at nearly the same time.

The weekly per-user booking limit is protected by a transaction-scoped
PostgreSQL advisory lock per user/week around the count-and-insert operation.
The regular unit suite verifies the lock call order; the Postgres concurrency
tests validate the weekly limit and single-winner slot booking against a real
database, and CI runs them.

Booking flows also use an in-process semaphore to avoid exhausting the database
pool during bursts of repeated Telegram interactions.

## Background Jobs

The scheduler is initialized on bot startup and shut down on bot shutdown. It
handles:

- weekly reset notifications and recurring slot state
- hourly and 15-minute reminders
- attendance and location-related checks

Reminder and check-in jobs select bookings by time window and persist what they
sent (`reminded_hourly_at`, `reminded_15_at`, `location_prompted`), so a missed or
repeated tick neither loses nor duplicates a message. Each job also holds a
PostgreSQL advisory lock while it runs.

The supported deployment is one bot replica. Advisory locks cover a brief overlap
during a deploy; running several replicas would additionally need shared FSM
storage and Telegram polling coordination.

## Testing And Quality Gates

The test suite covers services, handlers, keyboards, config parsing, reminder
behavior, scheduler setup, and migration metadata. CI runs:

- Ruff linting
- mypy type checking
- unit tests, including the Postgres-backed booking concurrency and reminder tests
- Alembic head checks
- migration smoke test against PostgreSQL
- application healthcheck
- Docker image build

## Deployment Shape

The default Docker Compose setup runs:

- one bot container
- one PostgreSQL container with a persistent volume

The bot container applies migrations before starting polling. Production
deployments should provide strong database credentials, real runtime config
values, and a single active bot process.
