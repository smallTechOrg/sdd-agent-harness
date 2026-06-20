#!/bin/sh
set -e

# Ensure runtime dirs exist (Render persistent disk or local volume)
mkdir -p /data/uploads /data/logs

# Run DB migrations on every startup — idempotent, safe for rolling restarts
/app/.venv/bin/alembic upgrade head

exec /app/.venv/bin/uvicorn data_analysis_agent.api:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}"
