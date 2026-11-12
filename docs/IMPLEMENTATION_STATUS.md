# Implementation status

Status as of delivery. "Verified" means exercised in this build: automated tests, a browser run over every page,
or the Docker stack started from scratch.

## Verified

| Area | How it was verified |
| --- | --- |
| Auth, JWT refresh, RBAC for 4 roles | backend tests (`test_auth_rbac.py`); browser logins for every demo account |
| Tenant and customer isolation | backend tests (`test_tenant_isolation.py`), second-tenant login |
| Policy engine (operators, priorities, missing facts, versions, dry run) | `test_policy_engine.py`, Policies page |
| Execution engine: auto, approval, reject, escalate, duplicate key, over-refundable, partial, state machine | `test_refund_execution.py` |
| PayPal SDK paths: success, PENDING, 4xx typed error, undecodable error, connection refused, timeout → reconcile with same `PayPal-Request-Id`, truncated 2xx, bad credentials | `test_refund_execution.py`, `test_payments_webhooks.py` with the SDK transport stub |
| Checkout create / capture and webhook verification + dedupe | `test_payments_webhooks.py` |
| Support graph and copilot in deterministic mode | `test_agents.py`; chat and copilot in the browser |
| Knowledge upload, versioning, retrieval, citations | `test_platform.py`; chat citations |
| AG Studio: 4 default pages render, edit / save / load layouts | browser run (dev server and Docker build) |
| Honest action cards, AG Studio adapter error handling | frontend tests (14) |
| Docker Compose: build, migrate, seed, login, analytics | full stack started from clean volumes |
| Lint and types | ruff, mypy (backend); `tsc --noEmit` (frontend) |

Totals: **66 backend tests, 14 frontend tests, all passing.**

## Built but not verified against the live service

These need credentials that were not available during the build. The code paths are tested with stubs, and the app
fails visibly (never fakes success) when the service is missing.

| Item | Needs |
| --- | --- |
| Live PayPal Sandbox checkout, capture, refund, refund read | `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` |
| Live webhook signature verification | `PAYPAL_WEBHOOK_ID` and a public URL |
| LLM-backed classification, replies, copilot reasoning, embeddings | `LLM_PROVIDER` + OpenAI or Gemini key |
| AG Studio AI agent panel | an LLM key on the backend |
| AG Studio without watermark | `VITE_AG_LICENSE_KEY` |

Recommended first check once keys are in: Part 2 of [DEMO_GUIDE.md](DEMO_GUIDE.md).

## Known limitations

- **INR in PayPal Sandbox:** many Sandbox merchant accounts cannot receive INR. Use `DEMO_CURRENCY=USD` for live
  money movement. If PayPal rejects a currency the app shows the rejection.
- **Embeddings without an LLM key** use a deterministic lexical hash (`local-hash@768`): retrieval works on shared
  words, not meaning. It is labelled in the knowledge base.
- **Deterministic mode** replies are templated. They are accurate but less natural than LLM replies.
- **Notifications** are in-app only (bell and lists). No email or SMS delivery.
- **Tokens** live in `localStorage` with 30-minute access tokens; there is no server-side revocation list or staff MFA.
- **Sample data** cannot be refunded through PayPal by design; demo real refunds with a Sandbox-paid order.
- **AG Studio bundle** is about 6.7 MB, lazy-loaded only on the Analytics route.
- **Reconciler** is a simple polling loop (one process). It is safe to run more than one because reconciliation is
  idempotent, but it does not use a job queue.
- Changing `EMBEDDING_DIMENSIONS` needs a new migration (fixed vector column size).

## Not done

- Production deployment manifests beyond Docker Compose (Kubernetes, managed secrets, TLS termination).
- Customer file attachments on tickets.
- Load testing.
