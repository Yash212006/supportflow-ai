#!/usr/bin/env bash
# One-time local (non-Docker) setup. Needs Python 3.12+, Node 20+, PostgreSQL 16 with pgvector, Redis.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { cp .env.example .env; echo "Created .env from .env.example"; }

python3 -m venv backend/.venv
(cd backend && .venv/bin/pip install -r requirements.lock.txt && .venv/bin/pip install pytest==9.2.0 pytest-cov==7.1.0 mypy==2.4.1 ruff==0.17.4)
(cd frontend && npm ci)

echo "Create the database if needed:"
echo "  createuser supportflow -P   (password: supportflow)"
echo "  createdb -O supportflow supportflow && psql -d supportflow -c 'CREATE EXTENSION IF NOT EXISTS vector'"
echo "Then: scripts/dev.sh"
