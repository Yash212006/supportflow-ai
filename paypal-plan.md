# PayPal integration plan and contract sheet

Written per the APIMatic PayPal Context Plugin (`paypal@context-plugins` v0.4.1) workflow
(`python-integrate-paypal` → `python-getting-started` → SDK map). Every row below is a lookup from the
SDK map (`sdk-map.md`, `map/operations/orders.md`, `map/operations/payments.md`) or from the model /
enum module the map names, in the generated SDK `paypal` v2.29
(`git+https://github.com/context-plugins/paypal-python-sdk.git@143e57f2`, vendored as a wheel in `backend/vendor/` for Docker builds).

## Host decisions

| Decision | Value | Source |
| --- | --- | --- |
| Sync or async | **Sync** `PaypalClient`. The backend is FastAPI with sync SQLAlchemy sessions and sync `def` route handlers (run in the threadpool), so the sync client fits; the async client is never used. | python-integrate-paypal step 2 |
| Client lifetime | One long-lived client per process, built lazily in `app/integrations/paypal/client.py` (`get_paypal_client()`), closed on app shutdown via `close()`. Rebuilt only when credentials change. | python-client-initialization |
| base_url | Always passed explicitly from `PAYPAL_BASE_URL` (default `https://api-m.sandbox.paypal.com`). Never omitted. | sdk-map "Servers & auth" |
| Auth | `oauth2=ClientCredentials(client_id=…, client_secret=…)` from settings. If either is empty, no client is built and every PayPal operation returns a typed `PayPalNotConfigured` (HTTP 503) instead of sending an unauthenticated request. | python-authentication "Notes" |
| Timeout | `timeout=20.0` (bounds each wait, not the call). Sync code: no whole-call budget. | sdk-map constructor table |
| Retries | Keep SDK default (GET/HEAD/PUT/OPTIONS retried on 408/429/5xx, max 3). POSTs (create, capture, refund) are **not** retried by the SDK; we make them safe with `PayPal-Request-Id` so a manual re-submit is idempotent at PayPal. | sdk-map "Retries" |

## Operations in scope

| Operation | Route | Signature (keyword-only after `*`) | Returns | Error union |
| --- | --- | --- | --- | --- |
| `client.orders.create_order` | `POST /v2/checkout/orders` | `create_order(body: OrderRequest \| OrderRequestDict, *, pay_pal_request_id=None, prefer="return=minimal", …)` | `Order` | `CreateOrderErrorBody` = `Error` [400,401,422] \| `RawError` |
| `client.orders.get_order` | `GET /v2/checkout/orders/{id}` | `get_order(id_: str, *, fields=None, …)` | `Order` | `GetOrderErrorBody` = `Error` [401,404] \| `RawError` |
| `client.orders.capture_order` | `POST /v2/checkout/orders/{id}/capture` | `capture_order(id_: str, *, pay_pal_request_id=None, prefer="return=minimal", body=None, …)` | `Order` | `CaptureOrderErrorBody` = `Error` [400,401,403,404,422,500] \| `RawError` |
| `client.payments.get_captured_payment` | `GET /v2/payments/captures/{capture_id}` | `get_captured_payment(capture_id: str, *, …)` | `CapturedPayment` | `Error` [401,403,404] \| `RawError` [500, other] |
| `client.payments.refund_captured_payment` | `POST /v2/payments/captures/{capture_id}/refund` | `refund_captured_payment(capture_id: str, *, pay_pal_request_id=None, prefer="return=minimal", body: RefundRequest \| RefundRequestDict \| None = None, …)` | `Refund` | `Error` [400,401,403,404,409,422] \| `RawError` [500, other] |
| `client.payments.get_refund` | `GET /v2/payments/refunds/{refund_id}` | `get_refund(refund_id: str, *, …)` | `Refund` | `Error` [401,403,404] \| `RawError` [500, other] |

We pass `prefer="return=representation"` on create/capture/refund so the response carries status,
amounts and links (the docstring documents `return=minimal` as default).

Full vs partial refund (docstring, `paypal/apis/payments.py`): *"For a full refund, include an empty
payload … For a partial refund, include an amount object."* We always send `amount` (exact value we
validated), plus `invoice_id`/`custom_id` = internal refund id and `note_to_payer`.

## Model members we set or read

| Model | Member (wire = python unless noted) | Required? |
| --- | --- | --- |
| `OrderRequest` | `intent: CheckoutPaymentIntentOrStr` (`CAPTURE`) · `purchase_units: list[PurchaseUnitRequest]` · `application_context: Optional[OrderApplicationContext]` | intent, purchase_units required |
| `PurchaseUnitRequest` | `amount: AmountWithBreakdown` (required) · `reference_id`, `custom_id`, `invoice_id`, `description` (Optional = UNSET) | amount required |
| `AmountWithBreakdown` / `Money` | `currency_code: str` · `value: str` | both required |
| `OrderApplicationContext` | `brand_name`, `return_url`, `cancel_url`, `user_action` (`OrderApplicationContextUserAction`, default `CONTINUE`; we use `PAY_NOW` wire value) | all optional |
| `RefundRequest` | `amount: Optional[Money]` · `custom_id` · `invoice_id` · `note_to_payer` | all optional |
| `Order` (response) | `id`, `status: OrderStatusOrStr`, `links: list[LinkDescription]`, `purchase_units[].payments.captures[]` (`OrdersCapture`) | all Optional (UNSET) → we assert `id` and `status` present |
| `CapturedPayment` | `id`, `status: CaptureStatusOrStr`, `amount: Money` | Optional → assert `id`, `status` |
| `Refund` | `id`, `status: RefundStatusOrStr`, `amount`, `status_details` | Optional → assert `id`, `status` |
| `Error` (typed error arm) | `name: str` · `message: str` · `debug_id: str` · `details: Optional[list[ErrorDetails]]` | name/message/debug_id required |

Optional here is `T | UnsetType`, never `None`. We build requests as `…Dict` TypedDicts and omit keys
rather than passing `None`.

Enums (from `paypal/models/enums/`):
- `OrderStatus`: CREATED, SAVED, APPROVED, VOIDED, COMPLETED, PAYER_ACTION_REQUIRED
- `CaptureStatus`: COMPLETED, DECLINED, PARTIALLY_REFUNDED, PENDING, REFUNDED, FAILED
- `RefundStatus`: CANCELLED, FAILED, PENDING, COMPLETED
- `CheckoutPaymentIntent`: CAPTURE, AUTHORIZE

Enums are open (`…OrStr`): an unknown wire value arrives as a plain `str`. We store `str(value.value if Enum else value)`.

## Error boundary (one place: `app/integrations/paypal/errors.py`)

Order of the ladder:
1. `ApiError` whose `.error` is `OAuthProviderError` → `PayPalAuthError` (configuration fault, nothing sent).
2. `ApiError` with `.error` an `Error` → `PayPalApiError(status, name, message, debug_id, details)`; outcome **known: rejected**.
3. `ApiError` with `RawError` → `PayPalApiError(status, text)`; 5xx marked `outcome_unknown` for writes.
4. `httpx2.ConnectError | ConnectTimeout | PoolTimeout | ProxyError` → `PayPalTransportError(sent=False)` known nothing happened.
5. other `httpx2.RequestError` → `PayPalTransportError(sent=True)` → outcome **unknown** → refund `OUTCOME_UNKNOWN`, action `PENDING_CONFIRMATION`, settled by reconcile (same `PayPal-Request-Id`), `get_refund` or a verified webhook. Never marked success.
6. `pydantic.ValidationError` / `ValueError` on 2xx → outcome unknown, same as 5.

`str(ApiError)` omits the body, so we log `.error` fields explicitly (never credentials).

## Webhook verification (not in this SDK)

The generated SDK covers 40 operations across orders/payments/subscriptions/transaction_search/vault and
has **no webhook-verification operation**. We call PayPal's documented
`POST /v1/notifications/verify-webhook-signature` directly with `httpx`, using a bearer token from
`POST /v1/oauth2/token` (client-credentials, cached until ~60 s before `expires_in`). Body: `auth_algo`,
`cert_url`, `transmission_id`, `transmission_sig`, `transmission_time` (from the `PAYPAL-*` headers),
`webhook_id` (from `PAYPAL_WEBHOOK_ID`), `webhook_event` (parsed JSON). Accept only
`verification_status == "SUCCESS"`. This row is **UNVERIFIED by the plugin** (outside SDK scope) and is
taken from PayPal's public REST docs; recorded in docs/APIMATIC_INTEGRATION.md as a limitation.

## DUPLICATE CLAIMS

| Write | Where the claim is stored | What rejects the second one | Where that rejection is caught | Where in the code |
| --- | --- | --- | --- | --- |
| Refund a capture | `execution_actions` row with UNIQUE `idempotency_key`, inserted in a savepoint before any policy evaluation or SDK call; then `payments` row locked (`SELECT … FOR UPDATE` key-share) while the refundable amount is recomputed, and the amount reserved in `payments.refunded_amount` before PayPal is called | PostgreSQL UNIQUE on `execution_actions.idempotency_key`; the row lock serialises concurrent refunds of one payment; revalidation rejects anything above the remaining refundable amount | `except IntegrityError` → returns the existing action marked `duplicate` | `app/workflows/execution_engine.py` `ExecutionEngine.request_refund` (claim) → `execute_refund` (revalidate + lock) → `app/integrations/paypal/gateway.py` `PayPalGateway.refund_capture` (SDK call, `pay_pal_request_id=action.idempotency_key`) |
| Capture an order | `payments.capture_claimed_at` + `status=CAPTURE_PENDING` via a conditional `UPDATE … WHERE status IN (CREATED, APPROVED) AND capture_claimed_at IS NULL` | the conditional UPDATE affects 0 rows for the second caller | `if not claimed:` returns the in-flight/captured payment or raises `Conflict` | `app/services/payments.py` `capture_paypal_order` (claim) → `PayPalGateway.capture_order` (SDK call, `pay_pal_request_id=capture-<payment id>`) |
| Create PayPal order | `payments` row inserted and committed with UNIQUE (`order_id`, `attempt`) before the call; an existing open checkout is reused | UNIQUE constraint `uq_payments_order_attempt` | `except IntegrityError` → `Conflict` | `app/services/payments.py` `create_paypal_checkout` → `PayPalGateway.create_order` |
| Webhook event processing | `webhook_events` row with UNIQUE `event_id`, written after the signature check runs (unverified events are stored as REJECTED and never applied) | UNIQUE constraint on `webhook_events.event_id` | `except IntegrityError` → event acknowledged as a duplicate, not re-applied | `app/services/payments.py` `ingest_webhook` (no SDK call; state sync through `ExecutionEngine.apply_refund_status`) |
| Reconcile an unknown refund outcome | no new claim: reuses the original action and its `idempotency_key` | PayPal returns the original refund for a repeated `PayPal-Request-Id` | n/a (state applied from PayPal's answer) | `ExecutionEngine.reconcile`, called by `POST /api/actions/{id}/reconcile` and `app/workers/reconcile.py` |

`PayPal-Request-Id` (= our idempotency key) is passed beside the claim on every POST, never in place of it.

## Assumptions & Blockers

- Blocker (environment): PayPal Sandbox credentials not yet provided. Integration is built and unit-tested
  against a fake transport; live sandbox lifecycle test runs when `PAYPAL_CLIENT_ID/SECRET` are set.
- Assumption: currency. The demo business is seeded in INR (`DEMO_CURRENCY=INR`). Many PayPal Sandbox
  merchant accounts cannot receive INR, so set `DEMO_CURRENCY=USD` and re-seed to demo live captures and
  refunds; orders carry their own currency and PayPal is always sent the order's currency. If PayPal
  rejects a currency, the rejection is shown as a failure, never converted silently.

## REQUIRED READING

- MUST load `python-getting-started` (loaded)
- MUST load `python-client-initialization` (loaded) — client construction / lifetime
- MUST load `python-authentication` (loaded) — oauth2 keyword, OAuthProviderError
- MUST load `python-calling-endpoints` — keyword-only tail, response modes
- MUST load `python-models` — UNSET vs None, Dict companions
- MUST load `python-error-handling` (loaded) — catch ladder above
- MUST load `python-configuration-resilience` — retries default, timeout semantics
- MUST load `python-testing` (loaded) — fake transport seam, token request first
