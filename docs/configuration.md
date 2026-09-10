# Configuration

Music Room Bot uses two configuration sources:

- environment variables for deployment-level settings
- database-backed runtime config for operational bot settings that admins may
  change without redeploying

Create `.env` from `.env.example` for local development.

## Required Environment Variables

| Name | Description | Example |
| --- | --- | --- |
| `BOT_TOKEN` | Telegram bot token from BotFather. Required to start polling. | `123456:token` |
| `DATABASE_URL` | Async PostgreSQL connection URL for local runs. Docker Compose sets this automatically for the bot container. | `postgresql+asyncpg://user:pass@localhost:5432/musicroom` |
| `TIMEZONE` | Time zone used for booking dates, reminders, and scheduled jobs. | `Asia/Almaty` |
| `ACCESS_FORM_URL` | Public or private form URL shown to users who need access. | `https://example.com/access-form` |

`postgres://` and `postgresql://` URLs are normalized to
`postgresql+asyncpg://` at startup.

## Optional Environment Variables

| Name | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Python log level. Valid values: `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`, `NOTSET`. |
| `BOT_TOKEN_FILE` | unset | Path to a file containing the bot token. `BOT_TOKEN` takes precedence. |
| `DATABASE_URL_FILE` | unset | Path to a file containing the database URL. `DATABASE_URL` takes precedence. |
| `DB_POOL_SIZE` | `20` | SQLAlchemy async engine pool size. |
| `DB_MAX_OVERFLOW` | `10` | Extra database connections allowed above the pool size. |
| `DB_POOL_TIMEOUT` | `30` | Seconds to wait for a database connection before timing out. |
| `RUNTIME_CONFIG_CACHE_TTL` | `30` | Seconds to cache runtime config values in process. Use `0` to disable caching. |
| `BOOKING_MAX_IN_FLIGHT` | `10` | Maximum concurrent booking flows admitted by the in-process gate. |
| `BOOKING_ACQUIRE_TIMEOUT_S` | `0.05` | Seconds a booking flow waits for the gate before returning a busy response. |
| `BOOKING_USER_COOLDOWN_S` | `2.0` | Per-user cooldown in seconds for booking entry points. |
| `EQUIPMENT_TOPIC_ID` | unset | Optional bootstrap fallback for `equipment_topic_id`. |

Application logs are always emitted as newline-delimited JSON. Each record
includes `timestamp`, `level`, `logger`, `event`, `message`, source location
fields, exception details when present, and any custom `extra={...}` fields.

Docker Compose also reads these Postgres variables:

| Name | Default | Description |
| --- | --- | --- |
| `POSTGRES_DB` | `musicroom` | Compose database name. |
| `POSTGRES_USER` | `musicroom` | Compose database user. |
| `POSTGRES_PASSWORD` | `musicroom` | Compose database password. Change this outside local development. |

## Runtime Config Keys

Runtime config values are stored in the `config` table and loaded through
`app/services/config_runtime.py`.

| Key | Default | Type | Description |
| --- | --- | --- | --- |
| `geo_radius` | `50.0` | float | Allowed check-in radius in meters. |
| `geo_center_lat` | unset | string/float | Latitude for attendance check-ins. Configure before enabling location verification. |
| `geo_center_lon` | unset | string/float | Longitude for attendance check-ins. Configure before enabling location verification. |
| `reminder_hours` | `2` | int | Hours before a booking when the early reminder should fire. |
| `late_minutes` | `10` | int | Minutes after booking start when a user may still check in. |
| `weekly_limit` | `2` | int | Weekly booking limit per user. |
| `slot_length` | `60` | int | Slot length in minutes. |
| `admin_chat_id` | unset | int | Telegram chat ID for admin notifications and review flows. |
| `access_chat_id` | unset | int | Telegram chat ID used for access-related posting. |
| `member_chat_id` | unset | int | Telegram member group chat ID. |
| `member_topic_id` | unset | int | Optional topic ID in the member group. |
| `equipment_topic_id` | unset | int or none | Optional topic ID for equipment request posts. |
| `rules_text` | `Need to be updated.` | string | Rules text shown by the bot. |

Chat and topic IDs may be cleared with an empty string or `none` where the admin
flow supports clearing.

## Bootstrap Values

`python -m app.bootstrap` runs migrations, seeds missing runtime config values,
creates default weekly slots, and optionally creates the first admin user.

`python -m app.seed` only seeds runtime config, weekly slots, and the optional
admin. It does not run migrations.

To override runtime config defaults during bootstrap, set:

```bash
BOOTSTRAP_CONFIG_<CONFIG_KEY>=value
```

Common bootstrap values:

| Name | Description |
| --- | --- |
| `BOOTSTRAP_CONFIG_ADMIN_CHAT_ID` | Initial admin chat ID. |
| `BOOTSTRAP_CONFIG_MEMBER_CHAT_ID` | Initial member group chat ID. |
| `BOOTSTRAP_CONFIG_MEMBER_TOPIC_ID` | Optional initial member topic ID. |
| `BOOTSTRAP_CONFIG_ACCESS_CHAT_ID` | Initial access chat ID. |
| `BOOTSTRAP_CONFIG_GEO_CENTER_LAT` | Initial attendance latitude. |
| `BOOTSTRAP_CONFIG_GEO_CENTER_LON` | Initial attendance longitude. |
| `BOOTSTRAP_CONFIG_EQUIPMENT_TOPIC_ID` | Initial equipment topic ID. |

Optional first-admin bootstrap values:

| Name | Description |
| --- | --- |
| `BOOTSTRAP_ADMIN_TG_ID` | Telegram user ID to make admin. If empty, no admin is created. |
| `BOOTSTRAP_ADMIN_TG_USERNAME` | Telegram username for the initial admin. |
| `BOOTSTRAP_ADMIN_FULL_NAME` | Display name for the corresponding user row. Defaults to `Bootstrap Admin`. |

## Sensitive Data

Do not commit real values for:

- Telegram bot tokens
- Telegram chat IDs or topic IDs from a private deployment
- room coordinates
- invite links
- private form URLs
- database credentials or dumps

Before publishing a repository, scan the full git history and rotate anything
that was ever committed.
