# Transaction Conventions

The codebase uses `AsyncSession` and SQLAlchemy 2.0-style statements. The main
rule is simple: reads do not commit, command services own their commit.

## Handler Boundary

Telegram handlers may open a session and pass it to services, but they should not
call `add()`, `delete()`, `commit()`, `rollback()`, or `flush()` directly.

Handlers are responsible for:

- parsing Telegram messages and callback data
- checking permissions
- calling service functions
- rendering replies and keyboards

Handlers are not responsible for:

- enforcing booking, admin, warning, swap, or equipment rules
- deciding transaction boundaries
- mutating ORM objects directly

## Service Function Types

Use these categories when adding or changing service functions.

### Query Services

Query services return data and never mutate state. They must not call `commit()`,
`rollback()`, `flush()`, `add()`, or `delete()`.

Examples:

- `get_user_bookings(db, user_id)`
- `is_slot_free(db, target_date, hour)`
- `get_working_hours(db, weekday)`

### Command Services

Command services perform one business operation and own the transaction for that
operation. They should commit exactly once on success and roll back only when they
catch a database exception they can translate into a domain result.

Examples:

- `safe_create_booking(...)`
- `delete_user_by_username(...)`
- `accept_swap_offer(...)`
- `set_admin_weekly_slot(...)`

The caller should treat the return value as the source of truth instead of
inspecting partially mutated ORM state.

### Orchestration Services

Orchestration services coordinate multiple command/query operations or external
I/O. They should keep database transactions short and avoid holding a transaction
open while sending Telegram messages unless the old behavior explicitly requires
that ordering.

Examples:

- scheduled jobs
- reminder processing
- geo check processing
- admin flows that notify both a member and an admin chat

## Concurrency Rules

Use the database as the final authority for invariants.

- Slot uniqueness is enforced by `uq_booking_date_hour`.
- Weekly per-user booking limits are serialized with a transaction-scoped
  PostgreSQL advisory lock per user/week before count-and-insert decisions.
- Scheduler jobs use session-level PostgreSQL advisory locks so multiple bot
  processes do not run the same scheduled job concurrently.

Application-layer checks are still useful for user-friendly messages, but they
must not be the only protection for critical invariants.

## Test Expectations

When a change touches state mutation, add service-level tests around the command
function. Handler tests should verify delegation and rendered messages, not ORM
write mechanics.

For race-sensitive booking behavior, use the opt-in Postgres concurrency test:

```bash
MUSICROOM_POSTGRES_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/musicroom_test \
python -m unittest tests/test_booking_concurrency_postgres.py
```

The test creates a temporary schema and drops it afterward, but the database URL
should still point at a disposable test database.
