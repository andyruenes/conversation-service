# syntax=docker/dockerfile:1
FROM astral/uv:python3.13-trixie-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install deps only — app/, alembic/ are bind-mounted by docker-compose.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,id=conversation_service_uv,sharing=locked \
    uv sync --frozen --no-dev --no-install-project

# alembic/ is bind-mounted; only the .ini is needed at build time.
COPY alembic.ini ./

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/app"]
