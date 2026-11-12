#!/usr/bin/env bash
# Lint, type-check and test everything. Backend tests use the `supportflow_test` database and a stubbed
# PayPal transport: they never call PayPal and never represent stubbed responses as real transactions.
set -euo pipefail
cd "$(dirname "$0")/.."
(cd backend && .venv/bin/ruff check app tests && .venv/bin/mypy app && .venv/bin/python -m pytest -q)
(cd frontend && npx tsc --noEmit && npx vitest run)
