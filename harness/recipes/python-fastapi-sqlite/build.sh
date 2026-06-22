#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "Building frontend..."
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..

echo ""
echo "Starting server..."
echo "  API:      http://localhost:8001/health"
echo "  Frontend: http://localhost:8001/app/"
echo ""
uv run python -m agent
