# Environment setup

## Option A: Docker Compose (recommended)

Requirements: Docker with Compose v2.

```bash
cp .env.example .env               # fill in what you have; blanks are fine
docker compose up -d --build       # db (pgvector), redis, backend, reconciler, frontend
docker compose run --rm seed       # labelled sample data (run once)
```

- Web app: http://localhost:8080 (nginx serves the build and proxies `/api` to the backend)
- API: http://localhost:8000 (OpenAPI docs at `/docs`)
- Change host ports with `WEB_PORT=… BACKEND_PORT=… docker compose up -d`.
- Re-seed from scratch: `scripts/reset-demo.sh docker`.
- After changing `VITE_AG_LICENSE_KEY`, rebuild the frontend: `docker compose build frontend && docker compose up -d frontend`.

The backend container runs `alembic upgrade head` on start. The `reconciler` service re-checks refunds whose PayPal
outcome is unknown every 2 minutes (`RECONCILE_INTERVAL_SECONDS`). The PayPal SDK is installed from the vendored
wheel in `backend/vendor/`, so the build needs PyPI and npm but not GitHub.

## Option B: Local

Requirements: Python 3.12+, Node 20+ (22 tested), PostgreSQL 16 with the `vector` extension, Redis 7.

```bash
scripts/setup-local.sh             # .env, backend venv, npm ci
# create the database once:
createuser supportflow -P          # password: supportflow
createdb -O supportflow supportflow
psql -d supportflow -c 'CREATE EXTENSION IF NOT EXISTS vector'
scripts/dev.sh                     # migrate, seed, API on :8000, web on :5173
```

Vite proxies `/api` and `/health` to `http://localhost:8000` (override with `VITE_PROXY_TARGET`).

### Tests

```bash
createdb -O supportflow supportflow_test
psql -d supportflow_test -c 'CREATE EXTENSION IF NOT EXISTS vector'
scripts/test.sh
```

Backend tests reset and seed `supportflow_test`, set dummy PayPal credentials and `LLM_PROVIDER=none`, and stub
only the PayPal HTTP transport.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `production` enforces a strong `JWT_SECRET` |
| `JWT_SECRET` | placeholder | HMAC key for tokens. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DATABASE_URL` | local Postgres | SQLAlchemy URL (`postgresql+psycopg://…`) |
| `REDIS_URL` | `redis://localhost:6379/0` | Rate limiting |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Allowed browser origins |
| `FRONTEND_URL` | `http://localhost:5173` | PayPal return / cancel URLs (local dev). Docker uses `http://localhost:8080`, or `DOCKER_FRONTEND_URL` if set |
| `PUBLIC_API_URL` | `http://localhost:8000` | Public base URL of the API |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | empty | Sandbox app credentials. Empty = PayPal disabled (visible failures, no fakes) |
| `PAYPAL_BASE_URL` | `https://api-m.sandbox.paypal.com` | Sandbox API host |
| `PAYPAL_WEBHOOK_ID` | empty | Needed to verify webhooks; without it webhooks are rejected |
| `PAYPAL_TIMEOUT_SECONDS` | `20` | Per-wait SDK timeout |
| `LLM_PROVIDER` | `none` | `openai`, `gemini` or `none` (deterministic mode) |
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL` | empty, `gpt-4o-mini`, `text-embedding-3-small` | OpenAI |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL` | empty, `gemini-flash-latest`, `models/gemini-embedding-001` | Gemini |
| `GEMINI_FALLBACK_MODEL` | `gemini-2.5-flash` | Tried automatically when the main model errors or times out; empty disables |
| `GEMINI_API_VERSION` | `v1beta` | Gemini Developer API version (`v1` lacks the `*-latest` aliases) |
| `GEMINI_USE_VERTEXAI` | `false` | `true` for Vertex AI express-mode keys. Use **Integrations → Test AI connection** to check a key |
| `EMBEDDING_DIMENSIONS` | `768` | Vector size stored in pgvector |
| `LLM_TIMEOUT_SECONDS` | `60` | Provider timeout before falling back |
| `VITE_AG_LICENSE_KEY` | empty | AG Studio licence (build-time, public). Empty = evaluation watermark |
| `VITE_API_URL` | empty | API origin if not served behind the same host |
| `DEMO_CURRENCY` | `INR` | Currency of seeded data; use `USD` for live Sandbox refunds |
| `RATE_LIMIT_PER_MINUTE`, `AUTH_RATE_LIMIT_PER_MINUTE` | `120`, `10` | Per-IP limits |
| `MAX_UPLOAD_MB` | `10` | Knowledge upload limit |
| `RECONCILE_INTERVAL_SECONDS` | `120` | Reconciler loop interval |

The vector column size is fixed by the migration, so changing `EMBEDDING_DIMENSIONS` needs a new migration. After
switching embedding provider at the same size, re-embed existing documents with `POST /api/knowledge/reembed`
(manager). Without an LLM provider, embeddings use a deterministic local lexical hash
(`local-hash@768`), which is labelled as such and is not semantic.

## PayPal Sandbox checklist

1. developer.paypal.com → Apps & Credentials → Sandbox → Create App → copy client ID and secret.
2. Webhooks on that app → URL `https://<public host>/api/paypal/webhooks` (ngrok or similar for local) → events
   `CHECKOUT.ORDER.*`, `PAYMENT.CAPTURE.*`, `PAYMENT.REFUND.*` → copy the webhook ID.
3. Sandbox → Accounts → note a **personal** buyer account's email and password for checkout.
4. Restart the backend; **Integrations** should show PayPal and webhooks as configured.
