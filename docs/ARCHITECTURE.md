# Architecture

## Components

```
 Browser (React 19 + Vite)                       FastAPI (Python 3.12)                       External
 ┌─────────────────────────┐   /api (JWT)   ┌───────────────────────────────────┐
 │ Customer portal         │ ─────────────► │ routes: auth, customer, manager,  │
 │ Manager console         │                │ paypal, platform, studio_ai       │
 │ AG Studio (analytics)   │                │                                   │
 │  └ SupportFlowAdapter ──┼─ /api/studio-ai│ agents/  (LangGraph)              │──► OpenAI / Gemini (optional)
 └─────────────────────────┘                │ policies/ (deterministic engine)  │
                                            │ workflows/execution_engine        │──► PayPal Sandbox
                                            │ integrations/paypal (APIMatic SDK)│    Orders v2, Payments v2,
                                            │ knowledge/ (RAG)  analytics/      │    verify-webhook-signature
                                            │ services/ audit, notifications    │
                                            └──────────┬───────────────┬────────┘
                                                       │               │
                                              PostgreSQL 16 + pgvector  Redis (rate limits)
                                            workers/reconcile.py (outcome-unknown refunds)
```

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite 7, Tailwind CSS 4, shadcn-style components, React Router, TanStack Query, Zustand, React Hook Form + Zod, Recharts, AG Studio 3.1 |
| API | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| Data | PostgreSQL 16 with pgvector; Redis 7 for rate limiting |
| AI | LangChain + LangGraph; OpenAI or Gemini through one provider abstraction (`app/agents/llm.py`), or none |
| Payments | PayPal Sandbox through the APIMatic-generated `paypal` Python SDK v2.29 |

## Backend modules

| Path | Responsibility |
| --- | --- |
| `app/core` | settings, DB session, JWT and password hashing, `Principal` + RBAC dependencies, error types, rate limiting |
| `app/models` | SQLAlchemy models: tenancy, commerce, support, governance, system |
| `app/api/routes` | HTTP layer only; every query is filtered by `principal.business_id` (and `customer_id` for customers) |
| `app/agents` | support graph (5 agents), manager copilot, tool registry with per-agent permissions, LLM abstraction |
| `app/policies` | pure rule evaluation (`engine.py`), fact building + risk scoring (`facts.py`), versioned storage (`service.py`) |
| `app/workflows/execution_engine.py` | action state machine, idempotency, approvals, revalidation, PayPal refund execution, reconciliation |
| `app/integrations/paypal` | SDK client lifecycle, gateway (only place the SDK is called), error ladder, webhook verification |
| `app/services` | payments + webhooks, PayPal transaction log, tickets, notifications, audit |
| `app/knowledge` | upload, extraction, chunking, embeddings, versioned retrieval |
| `app/analytics` | KPIs and the fixed-column datasets AG Studio reads |
| `app/workers/reconcile.py` | periodic re-check of refunds whose PayPal outcome is unknown |

## Data model (main tables)

- **Tenancy:** `businesses`, `users` (role), `customers` (optionally linked to a user).
- **Commerce:** `products`, `orders`, `order_items`, `shipments`, `payments` (source `PAYPAL_SANDBOX` or `SEED_SAMPLE`, `refunded_amount`, `capture_claimed_at`), `paypal_transactions` (every PayPal API call: operation, status, debug id, redacted bodies), `refunds`.
- **Support:** `support_tickets`, `ticket_events`, `conversations`, `messages`.
- **Governance:** `business_policies`, `policy_versions` (immutable), `policy_decisions` (inputs + full trace), `execution_actions` (UNIQUE `idempotency_key`, state history), `approval_requests`, `approval_actions`, `agent_executions`, `agent_tool_calls`.
- **System:** `knowledge_documents`, `knowledge_chunks` (pgvector), `webhook_events` (UNIQUE `event_id`), `notifications`, `audit_logs`, `dashboard_preferences`.

Every business table carries `business_id`. Sample rows carry `is_sample` and are labelled in the UI.

## Refund flow

```
customer chat / customer refund form / staff / copilot proposal
        │
        ▼
ExecutionEngine.request_refund ── claim: INSERT execution_actions (UNIQUE idempotency_key)
        │                         duplicate → return the existing action
        ▼
lock payment row ─► build facts + deterministic risk ─► PolicyEngine.evaluate (stored with trace)
        │
        ├─ REJECTED / NEEDS_MORE_INFORMATION ─► action REJECTED, customer told why
        ├─ ESCALATED ─────────────────────────► approval request (high risk) + ticket escalated
        ├─ REQUIRES_APPROVAL ─────────────────► approval request ─► manager approves ─┐
        └─ AUTO_EXECUTE ─────────────────────────────────────────────────────────────┤
                                                                                       ▼
                         execute_refund: re-lock + revalidate (ownership, captured, refundable, policy version,
                         real PayPal capture, PayPal configured) ─► EXECUTING ─► SDK refund_captured_payment
                                                                                       │ PayPal-Request-Id = idempotency key
            ┌──────────────────────────┬───────────────────────────────┬───────────────┴──────────────┐
         COMPLETED                  PENDING                 timeout / 5xx / unreadable          4xx rejection
         SUCCEEDED            PENDING_CONFIRMATION        PENDING_CONFIRMATION (OUTCOME_UNKNOWN)       FAILED
                                     └──── webhook (verified) / GET refund / reconcile worker ───┘
```

### Action state machine

| From | Allowed next states |
| --- | --- |
| REQUESTED | VALIDATING, CANCELLED |
| VALIDATING | APPROVED, REQUIRES_APPROVAL, REJECTED, ESCALATED, CANCELLED |
| REQUIRES_APPROVAL | APPROVED, REJECTED, CANCELLED |
| ESCALATED | APPROVED, REJECTED, CANCELLED |
| APPROVED | EXECUTING, REJECTED, FAILED |
| EXECUTING | SUCCEEDED, PENDING_CONFIRMATION, FAILED |
| PENDING_CONFIRMATION | SUCCEEDED, FAILED |
| FAILED | APPROVED (manual retry, only when PayPal never received the request) |
| SUCCEEDED, REJECTED, CANCELLED | terminal |

Any other transition raises `InvalidTransition`. Each transition is appended to the action's `history` with actor and time.

## Payment flow

1. Customer places an order (prices from the catalogue, never the client) → `PENDING_PAYMENT`.
2. `POST /api/customer/orders/{id}/pay` → payment row claimed (UNIQUE order + attempt) → SDK `create_order` → buyer redirected to PayPal.
3. Buyer returns to `/customer/checkout/return` → `POST .../capture` → conditional-update claim → SDK `capture_order`.
4. Order becomes `PAID` only when PayPal returns a `COMPLETED` capture. Verified webhooks (`CHECKOUT.ORDER.*`, `PAYMENT.CAPTURE.*`, `PAYMENT.REFUND.*`) keep state in sync.

## Request handling

- Middleware adds `X-Request-Id`, security headers and a JSON access log for `/api`.
- All errors leave as `{"error": {"code", "message", "details"}}`; unhandled exceptions are logged and returned as a generic 500 without internals.
- Sync route handlers run in FastAPI's threadpool with one SQLAlchemy session per request.
