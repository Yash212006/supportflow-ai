# PayPal integration

SupportFlow uses **PayPal Sandbox** only. All PayPal REST calls except webhook verification go through the
APIMatic-generated Python SDK (`paypal` v2.29), wrapped in one gateway class. The SDK contract (signatures, models,
error union, retry and timeout behaviour) is recorded in [`paypal-plan.md`](../paypal-plan.md).

## Setup

1. Sign in at developer.paypal.com → **Apps & Credentials** → Sandbox → create an app.
2. Copy the client ID and secret into `.env` (`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`).
3. Add a webhook on the app pointing to `https://<public host>/api/paypal/webhooks` (use a tunnel such as ngrok in
   development) with events `CHECKOUT.ORDER.APPROVED`, `CHECKOUT.ORDER.COMPLETED`, `PAYMENT.CAPTURE.*`,
   `PAYMENT.REFUND.*`. Put its ID in `PAYPAL_WEBHOOK_ID`.
4. Use a Sandbox **personal** account (from the Sandbox accounts page) to pay at checkout.
5. If your Sandbox merchant cannot receive INR, set `DEMO_CURRENCY=USD` and re-seed.

**Integrations** in the manager console shows whether PayPal and webhooks are configured (never the secrets).

## Operations used

| Use | SDK call | PayPal endpoint |
| --- | --- | --- |
| Start checkout | `orders.create_order` (intent CAPTURE, `PayPal-Request-Id`, `return=representation`) | `POST /v2/checkout/orders` |
| Read order | `orders.get_order` | `GET /v2/checkout/orders/{id}` |
| Capture | `orders.capture_order` (`PayPal-Request-Id = capture-<payment id>`) | `POST /v2/checkout/orders/{id}/capture` |
| Read capture | `payments.get_captured_payment` | `GET /v2/payments/captures/{id}` |
| Refund | `payments.refund_captured_payment` (exact `amount`, `invoice_id`, `note_to_payer`, `PayPal-Request-Id` = action idempotency key) | `POST /v2/payments/captures/{id}/refund` |
| Read refund | `payments.get_refund` | `GET /v2/payments/refunds/{id}` |
| Verify webhook | direct `httpx` (not in the SDK) | `POST /v1/notifications/verify-webhook-signature` |

The SDK client is built once per process (`app/integrations/paypal/client.py`) from settings, with the base URL
passed explicitly. If credentials are missing no client is built and every call raises `PayPalNotConfigured`
(HTTP 503 with a clear message); nothing is faked.

## Checkout

1. Customer clicks **Pay with PayPal**. A `payments` row is claimed (UNIQUE order + attempt) before the SDK call.
2. The buyer approves on PayPal and returns to `/customer/checkout/return`.
3. The app captures. The order becomes `PAID` only when PayPal returns a `COMPLETED` capture.
4. Declines show as failures with PayPal's reason. Timeouts leave the payment `CAPTURE_PENDING` until a read,
   **Sync from PayPal** (manager, payment detail) or a webhook settles it.

## Refunds

Refunds are never sent straight to PayPal from an API route or an agent. Every route (customer chat, customer form,
staff, `POST /api/paypal/captures/{id}/refund`, copilot proposal) creates an execution action that goes through the
policy engine. Immediately before calling PayPal the engine re-locks the payment and revalidates ownership, capture
status, refundable amount, policy version, that the payment is a real Sandbox capture and that PayPal is configured.

### Failure handling

| What happened | What the app records | What the user sees |
| --- | --- | --- |
| PayPal `COMPLETED` | refund `COMPLETED`, action `SUCCEEDED`, payment refunded amount updated | "Refund completed by PayPal" with the PayPal refund id |
| PayPal `PENDING` | refund `PENDING`, action `PENDING_CONFIRMATION` | "Refund pending at PayPal" |
| 4xx with PayPal error body | refund `FAILED`, PayPal name, message and debug id stored | "Refund could not be completed" + reason |
| Connection refused / DNS / bad credentials (nothing sent) | `FAILED` with a retryable code | Failure; manager may **Retry** |
| Timeout, 5xx, truncated or unreadable 2xx (may have been processed) | refund `OUTCOME_UNKNOWN`, action `PENDING_CONFIRMATION`, amount stays reserved | "Waiting for PayPal confirmation" |
| Duplicate request (same idempotency key) | existing action returned, no second PayPal call | the original result |

Outcome-unknown refunds are settled by a verified webhook, by **Reconcile** in the manager's refund view, or by
the `reconciler` worker (every 2 minutes in Docker). Reconcile re-sends the same request with the **same
`PayPal-Request-Id`**, so PayPal returns the original refund rather than creating a second one. The manual
**Retry** is only allowed when PayPal never received the request.

### Sample data

Seeded payments have `source = SEED_SAMPLE` and no PayPal capture. Approving a refund on one fails with
"This payment is labelled sample data (not a real PayPal Sandbox capture)…". To demo a real refund, pay for an
order through Sandbox checkout first.

## Webhooks

`POST /api/paypal/webhooks`:

1. Duplicate `event_id` already processed → acknowledged, no change.
2. Signature verified with PayPal (`auth_algo`, `cert_url`, `transmission_id`, `transmission_sig`,
   `transmission_time`, `webhook_id`, event). Only `verification_status == SUCCESS` is trusted. Without a
   configured webhook id the event is stored as `REJECTED` with `NOT_CONFIGURED`.
3. Verified events update the payment or refund through the same code paths as API responses, write an audit entry
   and notify the customer.

Handled (events that fail processing are kept as `FAILED` for replay, never half-applied): `CHECKOUT.ORDER.APPROVED`, `CHECKOUT.ORDER.COMPLETED`, `PAYMENT.CAPTURE.COMPLETED|PENDING|DENIED|DECLINED|REFUNDED|REVERSED`,
`PAYMENT.REFUND.PENDING|FAILED|CANCELLED|COMPLETED`. Others are stored as `IGNORED`.

## API log

Every SDK call writes a `paypal_transactions` row: operation, `PayPal-Request-Id`, HTTP status, resource id and
status, PayPal debug id, outcome, a sanitised response summary, error message and duration. No tokens, credentials
or full payloads are stored. Managers see it on each payment's detail page (**PayPal API log**) and in each refund's detail view.

## Testing

`backend/tests/paypal_stub.py` replaces only the SDK's HTTP transport (the seam the SDK documents for testing). The
real SDK builds every request and parses every response, so tests cover the token request, headers such as
`paypal-request-id`, typed error bodies, undecodable bodies, timeouts and connection failures. These stubbed
responses exist only inside tests and are never shown as real transactions.
