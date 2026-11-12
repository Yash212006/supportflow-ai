# API reference

Generated from the running FastAPI app (interactive docs at `http://localhost:8000/docs`, schema at `/openapi.json`). Regenerate with `cd backend && .venv/bin/python ../scripts/gen_api_reference.py > ../docs/API_REFERENCE.md`.

- Auth: `Authorization: Bearer <access token>` from `POST /api/auth/login` (refresh with `POST /api/auth/refresh`).
- Tenant isolation: every staff route is scoped to the caller's business; customers only see their own records.
- Errors: `{"error": {"code": str, "message": str, "details": any}}` with a matching HTTP status.
- Access levels: **customer**; **staff** = support agent, manager or admin; **manager** = manager or admin; **admin**; **public**.

## system

| Method | Path | Access | Notes |
| --- | --- | --- | --- |
| GET | `/health` | public |  |

## auth

| Method | Path | Access | Notes |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | public |  |
| GET | `/api/auth/me` | signed-in user |  |
| POST | `/api/auth/refresh` | public |  |
| POST | `/api/auth/register` | public | Public registration creates CUSTOMER accounts only. Staff accounts are created by admins. |

## customer

| Method | Path | Access | Notes |
| --- | --- | --- | --- |
| POST | `/api/customer/chat` | customer |  |
| GET | `/api/customer/conversations` | customer |  |
| GET | `/api/customer/conversations/{conv_id}` | customer |  |
| GET | `/api/customer/dashboard` | customer |  |
| GET | `/api/customer/orders` | customer |  |
| POST | `/api/customer/orders` | customer | Creates an internal order (PENDING_PAYMENT). Prices come from the catalogue, never the client. |
| GET | `/api/customer/orders/{order_id}` | customer |  |
| POST | `/api/customer/orders/{order_id}/pay` | customer | Creates a PayPal Sandbox order (Orders API v2) and returns the buyer approval URL. |
| GET | `/api/customer/payments` | customer |  |
| GET | `/api/customer/payments/{payment_id}` | customer |  |
| POST | `/api/customer/payments/{payment_id}/capture` | customer | Called after the buyer returns from PayPal approval. The capture result is PayPal's response. |
| GET | `/api/customer/products` | customer |  |
| GET | `/api/customer/refunds` | customer |  |
| POST | `/api/customer/refunds` | customer | Customer refund request. Goes through the policy engine and execution engine like every |
| GET | `/api/customer/tickets` | customer |  |
| POST | `/api/customer/tickets` | customer |  |
| GET | `/api/customer/tickets/{ticket_id}` | customer |  |
| POST | `/api/customer/tickets/{ticket_id}/escalate` | customer |  |
| POST | `/api/customer/tickets/{ticket_id}/rate` | customer |  |
| POST | `/api/customer/tickets/{ticket_id}/reopen` | customer |  |

## manager

| Method | Path | Access | Notes |
| --- | --- | --- | --- |
| GET | `/api/actions` | staff |  |
| POST | `/api/actions/{action_id}/reconcile` | manager |  |
| POST | `/api/actions/{action_id}/retry` | manager | Retry only when PayPal was never reached (not configured / connection refused). |
| GET | `/api/agents/executions` | staff |  |
| GET | `/api/agents/executions/{execution_id}` | staff |  |
| GET | `/api/approvals` | staff |  |
| GET | `/api/approvals/{approval_id}` | staff |  |
| POST | `/api/approvals/{approval_id}/approve` | manager |  |
| POST | `/api/approvals/{approval_id}/reject` | manager |  |
| GET | `/api/audit-logs` | manager |  |
| GET | `/api/customers` | staff |  |
| GET | `/api/customers/{customer_id}` | staff |  |
| GET | `/api/notifications` | signed-in user |  |
| POST | `/api/notifications/read-all` | signed-in user |  |
| POST | `/api/notifications/{notification_id}/read` | signed-in user |  |
| GET | `/api/orders` | staff |  |
| GET | `/api/orders/{order_id}` | staff |  |
| GET | `/api/orders/{order_id}/payments` | staff |  |
| GET | `/api/payments` | staff |  |
| GET | `/api/payments/{payment_id}` | staff |  |
| POST | `/api/payments/{payment_id}/sync` | manager | Reads the PayPal order (GET /v2/checkout/orders/{id}) and synchronises local state. |
| GET | `/api/policies` | staff |  |
| POST | `/api/policies` | manager |  |
| GET | `/api/policies/decisions` | staff |  |
| POST | `/api/policies/evaluate` | staff | Dry-run: evaluates without recording a decision or executing anything. |
| PUT | `/api/policies/{policy_id}` | manager | Editing rules creates a new immutable version; prior decisions keep pointing at the version used. |
| GET | `/api/refunds` | staff |  |
| POST | `/api/refunds` | staff | Staff-initiated refund proposal: still evaluated by the policy engine. |
| GET | `/api/refunds/{refund_id}` | staff |  |
| GET | `/api/staff` | staff |  |
| GET | `/api/tickets` | staff |  |
| GET | `/api/tickets/{ticket_id}` | staff |  |
| PATCH | `/api/tickets/{ticket_id}` | staff |  |

## paypal

| Method | Path | Access | Notes |
| --- | --- | --- | --- |
| POST | `/api/paypal/captures/{capture_id}/refund` | staff | Refund request against a capture. Routed through policy + execution engine, never direct. |
| POST | `/api/paypal/orders` | staff | Create a PayPal order for an internal order (e.g. to send a payment link). |
| GET | `/api/paypal/orders/{paypal_order_id}` | staff |  |
| POST | `/api/paypal/orders/{paypal_order_id}/capture` | manager |  |
| GET | `/api/paypal/refunds/{paypal_refund_id}` | staff | Reads GET /v2/payments/refunds/{id} and synchronises the local refund. |
| GET | `/api/paypal/status` | staff |  |
| POST | `/api/paypal/webhooks` | public, PayPal signature verified | PayPal webhook receiver. Unverified events are stored as REJECTED and never applied. |
| GET | `/api/paypal/webhooks/events` | manager |  |

## platform

| Method | Path | Access | Notes |
| --- | --- | --- | --- |
| GET | `/api/agents/copilot/conversations` | staff |  |
| GET | `/api/agents/copilot/conversations/{conv_id}` | staff |  |
| POST | `/api/agents/copilot/run` | staff |  |
| POST | `/api/agents/support/run` | customer |  |
| GET | `/api/analytics/ai-operations` | staff |  |
| GET | `/api/analytics/datasets` | staff | All AG Studio data sources in one call (authorised, tenant-scoped, fixed column sets). |
| GET | `/api/analytics/overview` | staff |  |
| GET | `/api/analytics/payments` | staff |  |
| GET | `/api/analytics/refunds` | staff |  |
| GET | `/api/analytics/risk` | staff |  |
| GET | `/api/analytics/support` | staff |  |
| GET | `/api/dashboards` | staff |  |
| POST | `/api/dashboards` | staff |  |
| DELETE | `/api/dashboards/{dash_id}` | staff |  |
| GET | `/api/dashboards/{dash_id}` | staff |  |
| GET | `/api/integrations/status` | staff |  |
| GET | `/api/knowledge/documents` | staff |  |
| DELETE | `/api/knowledge/documents/{doc_id}` | manager |  |
| GET | `/api/knowledge/documents/{doc_id}` | staff |  |
| POST | `/api/knowledge/reembed` | manager |  |
| POST | `/api/knowledge/search` | staff |  |
| POST | `/api/knowledge/upload` | manager |  |

## ag-studio

| Method | Path | Access | Notes |
| --- | --- | --- | --- |
| GET | `/api/studio-ai/config` | staff |  |
| POST | `/api/studio-ai/turn` | staff |  |

