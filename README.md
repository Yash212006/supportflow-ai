# SupportFlow AI

Autonomous customer support and financial operations for online businesses, built for the PayPal AI Hackathon.

Customers chat with an AI support team that looks up their real orders, payments and shipments, answers from a
versioned knowledge base, and can request refunds or cancellations. Every financial action goes through a
**deterministic, versioned policy engine** and an **execution state machine** before PayPal is called. Small
refunds can run automatically, mid-sized ones wait in an approval center, and large or risky ones are escalated.
Managers get an operations console, a read-only AI copilot and AG Studio dashboards.

> **Honesty rules built into the product.** A payment or refund is only shown as successful when PayPal says so
> (API response or verified webhook). An LLM reply is never treated as proof of anything. Seeded records are
> labelled *Sample data* everywhere and can never be refunded through PayPal. With no PayPal credentials the app
> runs, but every PayPal action fails visibly with "not configured".

## What's inside

| Area | Highlights |
| --- | --- |
| Customer portal | Shop and PayPal Sandbox checkout, orders, payments, AI support chat with citations and live action cards, tickets, refunds |
| Manager console | Overview KPIs, approval center with policy trace and live re-check, tickets, orders, customers, payments, PayPal API log, refunds (reconcile / retry), AI operations trace, policy editor with dry run, knowledge base, risk monitor, audit log, integrations |
| AI agents (LangGraph) | Orchestrator, Order investigation, Policy intelligence, Risk assessment, Resolution, Manager copilot; plus the AG Studio dashboard agent. Each has its own tool allow-list |
| Policy engine | Ordered rules over a fact catalog, 11 operators, 5 outcomes, immutable versions, full evaluation trace stored with every decision |
| Execution engine | Idempotent actions (UNIQUE key), row locks, revalidation right before PayPal, OUTCOME_UNKNOWN handling, reconciliation with the same `PayPal-Request-Id` |
| PayPal | Orders v2 create / get / capture, Payments v2 refund / get refund / get capture via the APIMatic-generated Python SDK; webhooks verified with PayPal's verify-webhook-signature API |
| Analytics | AG Studio (`/manager/analytics`) with Financial, Support, AI Ops and Risk default pages, saved layouts, SupportFlow theme, and the AG Studio AI agent through a backend LLM proxy |
| Knowledge (RAG) | PDF / DOCX / Markdown / text upload, chunking, pgvector embeddings, versioned documents, citations |
| Security | JWT access + refresh, bcrypt, RBAC (customer / agent / manager / admin), tenant isolation on every query, rate limiting (Redis), audit log, no secrets in the browser |

## Quick start (Docker)

```bash
cp .env.example .env              # optional: add PayPal Sandbox + LLM keys
docker compose up -d --build
docker compose run --rm seed      # labelled sample data, once
open http://localhost:8080
```

Demo accounts (all sample data):

| Role | Email | Password |
| --- | --- | --- |
| Customer | `priya@customer.demo` (also `arjun@`, `meera@`) | `Customer@123` |
| Support manager | `manager@supportflow.demo` | `Demo@12345` |
| Support agent | `agent@supportflow.demo` | `Demo@12345` |
| Admin | `admin@supportflow.demo` | `Demo@12345` |
| Second tenant (isolation demo) | `manager@contoso.demo` | `Demo@12345` |

The login page has one-click buttons for these. Local development without Docker is in
[docs/ENVIRONMENT_SETUP.md](docs/ENVIRONMENT_SETUP.md).

## What needs your credentials

| Feature | Without credentials | With credentials |
| --- | --- | --- |
| PayPal checkout, capture, refunds, webhooks | Fails visibly: "PayPal Sandbox is not configured". Sample payments cannot be refunded | Real Sandbox calls. Set `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_WEBHOOK_ID` |
| AI text (chat wording, copilot reasoning, AG Studio agent) | Deterministic mode: rule-based classification and templated replies, labelled "Deterministic" in the UI. AG Studio AI panel disabled | `LLM_PROVIDER=openai` or `gemini` plus the key |
| AG Studio | Fully working with an evaluation watermark | `VITE_AG_LICENSE_KEY` removes the watermark |

**Currency:** sample data is seeded in INR (policy thresholds ₹1,000 / ₹5,000). Many PayPal Sandbox merchant
accounts cannot receive INR; set `DEMO_CURRENCY=USD` and re-seed (`scripts/reset-demo.sh`) to demo live
captures and refunds (thresholds become $50 / $250).

## How PayPal is used

All PayPal calls run in the **PayPal Sandbox** from the backend only, through the **APIMatic-generated PayPal Server
SDK for Python** (`paypal` v2.29, vendored in `backend/vendor/`). Details: [PAYPAL_INTEGRATION](docs/PAYPAL_INTEGRATION.md).

| Step in the product | PayPal API |
| --- | --- |
| Customer checks out | Orders v2 `POST /v2/checkout/orders` (create, with `PayPal-Request-Id`) |
| Buyer returns from PayPal | Orders v2 `POST /v2/checkout/orders/{id}/capture`, `GET /v2/checkout/orders/{id}` |
| Approved or auto-executed refund | Payments v2 `POST /v2/payments/captures/{id}/refund` with the action's idempotency key as `PayPal-Request-Id` |
| Re-check before refunding, reconcile unknown outcomes | Payments v2 `GET /v2/payments/captures/{id}`, `GET /v2/payments/refunds/{id}` |
| Webhooks (`PAYMENT.CAPTURE.*`, `PAYMENT.REFUND.*`, `CHECKOUT.ORDER.*`) | `POST /v1/notifications/verify-webhook-signature` before any event is applied |

A payment or refund is only marked successful from a PayPal API response or a signature-verified webhook.

## How AI is used

| Where | Model / service | What it does | What it can never do |
| --- | --- | --- | --- |
| Customer support chat | Google **Gemini** (`gemini-flash-latest`, automatic fallback to `gemini-2.5-flash`) or OpenAI `gpt-4o-mini`, orchestrated with **LangGraph** | Classifies intent, extracts order numbers, writes the reply from a fact sheet built by database tools | Decide or execute a refund, or claim one happened |
| Knowledge base (RAG) | Gemini `gemini-embedding-001` (768-d) or OpenAI embeddings, stored in **pgvector** | Retrieves policy passages with citations | |
| Manager copilot | Same LLM with read-only tools | Answers ops questions, drafts refund proposals as dry runs | Submit without the policy engine |
| AG Studio AI panel | Same LLM through a backend proxy | Builds dashboard widgets from natural language | Call financial tools (rejected by name) |

Every money decision comes from the deterministic, versioned policy engine; the AI proposes, the policy engine
decides, PayPal confirms. With no key the app runs in a labelled **Deterministic mode**. Details:
[AGENT_ARCHITECTURE](docs/AGENT_ARCHITECTURE.md).

## Sponsor tools

| Tool | Used for |
| --- | --- |
| **APIMatic** | The APIMatic-generated PayPal Python SDK makes every PayPal REST call; the APIMatic PayPal context-plugin skills were used to look up the SDK contract ([APIMATIC_INTEGRATION](docs/APIMATIC_INTEGRATION.md)) |
| **Render** | Optional free hosting via the `render.yaml` Blueprint (see below) |

## Deploy a free demo on Render

Full beginner guide: [docs/DEPLOY.md](docs/DEPLOY.md).


1. Push this repo to GitHub. On render.com: **New → Blueprint** → pick the repo. It creates Postgres, Key Value
   (Redis), the API (Docker) and the web app (static site), all on free plans.
2. When prompted, fill the `sync: false` values. On the first pass you don't know the URLs yet: leave
   `FRONTEND_URL`, `CORS_ORIGINS`, `PUBLIC_API_URL` and `VITE_API_URL` blank, deploy, then set them from the two
   service URLs (`https://supportflow-web…onrender.com`, `https://supportflow-api…onrender.com`) and redeploy both.
3. Sample data is loaded on first start (`SEED_ON_START=true`, `DEMO_CURRENCY=USD`).
4. In the PayPal app, add the webhook `https://<api url>/api/paypal/webhooks` and set `PAYPAL_WEBHOOK_ID`.

Free services sleep when idle: the first request after a while takes about a minute. The reconciler worker is not
part of the free Blueprint; managers can reconcile pending refunds from **Refunds**.

## Tests

```bash
scripts/test.sh     # ruff, mypy, 66 backend tests (Postgres), tsc, 14 frontend tests
```

Backend tests run against a real PostgreSQL test database and stub only the PayPal HTTP transport, so the real
SDK builds and parses every request. Stubbed responses are never shown as real transactions.

## Documentation

| Doc | Contents |
| --- | --- |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | System design, data model, request flows |
| [AGENT_ARCHITECTURE](docs/AGENT_ARCHITECTURE.md) | The agents, tools, permissions and tracing |
| [POLICY_ENGINE](docs/POLICY_ENGINE.md) | Rules, facts, operators, versions, default policies |
| [PAYPAL_INTEGRATION](docs/PAYPAL_INTEGRATION.md) | Checkout, capture, refunds, webhooks, failure handling |
| [APIMATIC_INTEGRATION](docs/APIMATIC_INTEGRATION.md) | Exactly what APIMatic tooling was and was not used for |
| [AG_GRID_INTEGRATION](docs/AG_GRID_INTEGRATION.md) | AG Studio dashboards, data sources, AI adapter |
| [SECURITY](docs/SECURITY.md) | Auth, RBAC, tenancy, secrets, AI guardrails |
| [ENVIRONMENT_SETUP](docs/ENVIRONMENT_SETUP.md) | Docker and local setup, every environment variable |
| [DEMO_GUIDE](docs/DEMO_GUIDE.md) | A scripted hackathon demo |
| [API_REFERENCE](docs/API_REFERENCE.md) | Every endpoint with its access level |
| [DEPLOY](docs/DEPLOY.md) | Free hosted demo on Render, step by step |
| [IMPLEMENTATION_STATUS](docs/IMPLEMENTATION_STATUS.md) | What is done, verified, and not done |
| [paypal-plan.md](paypal-plan.md) | SDK contract sheet and duplicate-claim table |

## Repository layout

```
backend/    FastAPI app (app/), Alembic migrations, tests, vendored PayPal SDK wheel
frontend/   React + Vite app (src/pages/customer, src/pages/manager, src/integrations/ag-studio)
docs/       Documentation
scripts/    setup-local.sh, dev.sh, test.sh, reset-demo.sh, gen_api_reference.py
docker-compose.yml, render.yaml, .env.example
```

## License

[MIT](LICENSE). The vendored PayPal SDK wheel keeps its own MIT licence (`backend/vendor/PAYPAL_SDK_LICENSE`).
