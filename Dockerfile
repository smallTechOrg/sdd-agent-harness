FROM python:3.12-slim

# Install uv for reproducible dependency installs
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

# Disable uv's venv relinking — we copy files, not symlinks
ENV UV_LINK_MODE=copy
ENV UV_COMPILE_BYTECODE=1

# Layer 1: install third-party deps only (cache busts only on lock file change,
# not on application source changes). --no-install-project skips the local package.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Layer 2: application source (changes most frequently — keeps layer 1 cached)
COPY alembic.ini alembic.ini
COPY alembic/ alembic/
COPY src/ src/

# Layer 3: install the local package itself (fast — deps are already installed)
RUN uv sync --frozen --no-dev

# Runtime defaults — override these with Render env vars or docker run -e
ENV DATAANALYSIS_DATABASE_URL=sqlite:////data/app.db
ENV DATAANALYSIS_CHECKPOINT_DB=/data/checkpoints.db
ENV DATAANALYSIS_UPLOAD_DIR=/data/uploads
ENV DATAANALYSIS_LOG_FILE=/data/logs/app.log
ENV DATAANALYSIS_LOG_LEVEL=INFO

EXPOSE 8000

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
