#!/usr/bin/env bash
# Wipe and re-seed the labelled sample data. Local: scripts/reset-demo.sh   Docker: scripts/reset-demo.sh docker
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "docker" ]; then
  docker compose run --rm seed python -m app.seed --reset
else
  (cd backend && .venv/bin/python -m app.seed --reset)
fi
