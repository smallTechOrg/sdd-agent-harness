# syntax=docker/dockerfile:1

# ---- Stage 1: build the Next.js static export (frontend/out) ----
FROM node:20-slim AS frontend
WORKDIR /build/frontend
RUN npm install -g pnpm@9
# Install deps first for layer caching
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
# Build the static export → /build/frontend/out (next.config: output "export", basePath "/app")
COPY frontend/ ./
RUN pnpm build

# ---- Stage 2: python runtime ----
FROM python:3.12-slim AS runtime
# uv (fast, lockfile-driven installs)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    AGENT_LLM_PROVIDER=gemini

# Install runtime deps from the lockfile (no dev deps) — cached unless deps change
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Application code + migrations
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Built frontend from stage 1 — backend serves this at /app when present
COPY --from=frontend /build/frontend/out ./frontend/out

# SQLite lives here (ephemeral on Render — matches the app's session-only design)
RUN mkdir -p ./data

EXPOSE 8001
# Render injects $PORT; the app reads it (src/__main__.py). Run migrations, then serve.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run python -m src"]
