#!/bin/sh
# Container entrypoint: migrate, optionally seed labelled sample data, then serve on $PORT (default 8000).
set -e
alembic upgrade head
if [ "${SEED_ON_START:-false}" = "true" ]; then
  # No-op when data already exists; never blocks the API from starting.
  python -m app.seed || echo "seed: skipped (see message above)"
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
