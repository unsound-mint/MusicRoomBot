# Contributing

## Development

Use the commands documented in `README.md` and `AGENTS.md`.

Before opening a pull request, run:

```bash
uv run ruff check app tests
uv run mypy app
uv run python -m unittest discover -s tests
```

Model changes require an Alembic migration. Business logic belongs in
`app/services/`; Telegram handlers should stay focused on interaction flow.

## Sensitive Data

Do not commit `.env`, database dumps, Telegram chat IDs from a private
deployment, real geo coordinates for a private room, bot tokens, invite links, or
private form URLs.
