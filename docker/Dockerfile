FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml .
COPY app ./app
COPY tests ./tests
COPY scripts ./scripts
COPY alembic.ini .
COPY alembic ./alembic

RUN pip install --no-cache-dir ".[dev]"

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
