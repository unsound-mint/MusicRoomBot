# Deployment

Music Room Bot is designed to run as one long-lived Telegram polling process
with PostgreSQL. The included Docker Compose setup is suitable for local testing
and small self-hosted deployments after credentials and runtime config values
are replaced.

## Deployment Model

Run exactly one active bot replica.

The bot uses Telegram polling and starts APScheduler jobs in process. Multiple
active replicas can duplicate scheduled reminders, weekly reset messages, and
attendance checks unless scheduling and polling are redesigned for distributed
execution.

## Docker Compose

1. Create `.env` from `.env.example`.
2. Set at least `BOT_TOKEN`, `TIMEZONE`, and strong Postgres credentials.
3. Start the stack:

```bash
docker compose up -d --build
```

The Compose file sets explicit DNS resolvers for containers using
`DOCKER_DNS_PRIMARY` and `DOCKER_DNS_SECONDARY` from `.env`, defaulting to
`1.1.1.1` and `8.8.8.8`.

The Compose stack starts:

- `bot` - the application container
- `postgres` - PostgreSQL 16 with a named volume

The bot container builds from `Dockerfile` and starts with:

```bash
python -m app.migrate && exec python -m app.bot.main
```

This applies Alembic migrations before polling starts.

## First-Time Setup

After the database is reachable, seed default runtime config and weekly slots:

```bash
docker compose run --rm bot python -m app.seed
```

For a one-shot bootstrap that runs migrations and seed logic:

```bash
docker compose run --rm bot python -m app.bootstrap
```

Set `BOOTSTRAP_ADMIN_TG_ID` before seeding if you want to create the first admin
without editing the database manually.

## VPS Deployment Notes

A minimal VPS deployment needs:

- Docker and Docker Compose
- persistent storage for the Postgres volume
- outbound network access to Telegram
- backups for Postgres data
- process monitoring for the Compose stack

Operational checklist:

```bash
docker compose pull
docker compose up -d --build
docker compose logs -f bot
docker compose ps
```

Use `.env` for deployment settings, but keep it outside git. For Docker secret
mounts or platform-provided secret files, set `BOT_TOKEN_FILE` or
`DATABASE_URL_FILE`.

## Platform Deployment Notes

The app can run on platforms such as Fly.io, Railway, Render, or a container
host if the platform provides:

- one always-on worker/container
- PostgreSQL
- persistent environment variables or secret files
- a way to run migrations before the bot starts

Do not configure horizontal autoscaling for the bot process unless you first
move scheduled jobs to a distributed scheduler and switch Telegram delivery to a
deployment model that supports multiple workers safely.

## Database Migrations

Alembic migration files are stored in `alembic/versions/`.

Useful commands:

```bash
uv run alembic heads
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"
```

Every model/schema change should include a migration. CI checks that Alembic has
a head and applies migrations against PostgreSQL.

## Healthcheck

The Docker image defines:

```bash
python -m app.healthcheck
```

The healthcheck validates required startup configuration. In CI it is run after
migrations to catch missing bot or database settings.

## Production Hardening

Before production use:

- replace default Compose database credentials
- configure real runtime chat IDs, topic IDs, and geo coordinates
- keep `BOT_TOKEN`, `.env`, database dumps, and invite links out of git
- rotate any secret that ever appeared in history
- back up PostgreSQL regularly
- keep one active bot replica
- verify reminders and attendance checks after deployment
