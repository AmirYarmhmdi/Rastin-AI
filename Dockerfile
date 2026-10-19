# File guide.
# Use: Builds the production Rastin-AI container image.
# Usage: Docker Compose and Docker can build this file from the repo root.
# Duties: Installs dependencies, copies source code, and starts Uvicorn.
# Depends on: pyproject.toml, uv.lock, README.md, LICENSE, alembic, and src.

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.13 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

RUN groupadd --system app && \
    useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app && \
    mkdir -p /app/storage && \
    chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "rastin_ai.main:app", "--host", "0.0.0.0", "--port", "8000"]
