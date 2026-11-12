#!/usr/bin/env bash
# Run migrations, seed sample data (once), then start the API (:8000) and the web app (:5173).
set -euo pipefail
cd "$(dirname "$0")/.."
(cd backend && .venv/bin/alembic upgrade head && .venv/bin/python -m app.seed)
(cd backend && exec .venv/bin/uvicorn app.main:app --reload --port 8000) &
API=$!
trap 'kill $API 2>/dev/null' EXIT
cd frontend && npx vite --port 5173
