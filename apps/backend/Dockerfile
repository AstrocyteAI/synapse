FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY pyproject.toml .
COPY uv.lock* .

# Install dependencies (no editable install in production)
RUN uv sync --frozen --no-dev

# Copy application code
COPY synapse/ synapse/
COPY alembic.ini .

# Run migrations then start server
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn synapse.main:app --host 0.0.0.0 --port 8000"]
