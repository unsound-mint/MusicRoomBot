FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml README.md requirements.lock ./
RUN pip install --upgrade pip \
    && pip install -r requirements.lock

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

USER app

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -m app.healthcheck

CMD ["sh", "-c", "python -m app.migrate && exec python -m app.bot.main"]
