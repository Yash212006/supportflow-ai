# Security

## Authentication

- Passwords hashed with bcrypt (cost 12). Registration requires 8–128 characters.
- JWT (HS256) access tokens (30 minutes) and refresh tokens (7 days), each with a `type` claim that is checked, so a
  refresh token cannot be used as an access token.
- Every request reloads the user; deactivated users are rejected immediately.
- Public registration only creates **customer** accounts. Staff accounts are seeded or created by admins.
- Login and refresh are rate-limited per IP (`AUTH_RATE_LIMIT_PER_MINUTE`, default 10); all API routes share a
  per-IP limit (`RATE_LIMIT_PER_MINUTE`, default 120). Limits are kept in Redis.
- In `ENVIRONMENT=production` the API refuses to start with the default or a short `JWT_SECRET`.

## Authorization (RBAC)

| Role | Can |
| --- | --- |
| Customer | own orders, payments, refunds, tickets and chat only |
| Support agent | read the business's operations data, work tickets, use the copilot; cannot approve refunds or edit policies |
| Support manager | everything an agent can, plus approve / reject refunds, reconcile / retry, edit policies, manage knowledge |
| Admin | everything a manager can |

Enforced server-side by `require_customer`, `require_staff`, `require_manager`, `require_admin`
(`app/core/deps.py`). The UI hides controls by role, but the API is the boundary. `docs/API_REFERENCE.md` lists the
access level of every endpoint; only health, login, refresh, register and the signature-verified PayPal webhook are
public.

## Tenant isolation

Every business table carries `business_id`. Every staff query filters on the principal's `business_id`, and
customer queries also filter on `customer_id`. Lookups by id return 404 (not 403) for other tenants' records so ids
cannot be probed. Agent tools receive a scoped `ToolContext` and cannot reach outside it. Tests log in as the
second tenant (`manager@contoso.demo`) and as other customers to prove this.

## Financial safety

- The policy engine is deterministic and the execution engine calls it itself; no API route or agent can call
  PayPal's refund operation directly.
- Idempotency: UNIQUE `execution_actions.idempotency_key`, row locks on the payment, and `PayPal-Request-Id`.
- Revalidation right before every PayPal call (ownership, capture status, refundable amount, policy version, real
  Sandbox capture).
- Success is only recorded from a PayPal API response or a signature-verified webhook. Unknown outcomes stay
  pending and are reconciled with the same request id.
- Webhooks: signature verified with PayPal; unverified events are stored as rejected and never applied; duplicate
  event ids are no-ops.
- Amounts come from the database (catalogue prices, captured amounts), never from the client or the model.

## AI guardrails

- Agents have per-agent tool allow-lists; refused calls are recorded.
- The LLM never decides money: classification and wording only. Facts come from tools; decisions from the policy engine.
- Customer-facing action cards show execution-engine state, never model text.
- The reply prompt forbids claiming an action happened unless the resolution says so and forbids revealing rule ids,
  risk scores or internal reasoning.
- No chain-of-thought is requested, stored or displayed; traces hold code-written summaries.
- The AG Studio agent only receives dashboard tools; financial tool names are rejected.
- Uploaded knowledge documents are treated as reference text in prompts, not as instructions.

## Secrets

- All credentials come from environment variables (`.env`, never committed; `.env.example` has blanks only).
- PayPal and LLM keys exist only in the backend. The browser receives JWTs and the AG Studio licence key, which is
  public by design.
- The PayPal API log stores a sanitised summary (status, ids, debug id), never tokens, credentials or full payloads.
- Integrations status endpoints report *whether* something is configured, never its value.
- Errors returned to clients are generic for unexpected failures; details go to server logs.

## Input handling

- Pydantic validation on every body; consistent error envelope.
- Knowledge uploads: extension allow-list (PDF, DOCX, TXT, Markdown), magic-byte checks for PDF/DOCX, UTF-8 for
  text, size limit (`MAX_UPLOAD_MB`).
- SQL via SQLAlchemy parameters only.
- React escapes all rendered text; no `dangerouslySetInnerHTML` for user or model content.

## HTTP

CORS restricted to `CORS_ORIGINS`; `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`; request ids on every response. The backend container runs as a
non-root user.

## Audit

`audit_logs` records logins and registrations, orders, PayPal order creation and captures, refunds (requested,
PayPal response, outcome unknown, status synced, failed), approvals and rejections, policy versions, knowledge
uploads and deletions, ticket changes and rejected webhooks, each with actor, summary and structured details. Managers can browse it
under **Audit log**.

## Known gaps

- Access tokens are stateless; logout clears them client-side and they expire after 30 minutes (no server-side revocation list).
- Tokens are stored in `localStorage`; an XSS bug would expose them. There is no `dangerouslySetInnerHTML` in the app, but HTTP-only cookies would be stronger.
- No MFA for staff.
