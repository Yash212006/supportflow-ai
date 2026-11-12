# APIMatic integration

This page says exactly what APIMatic tooling was used for, so nothing is over-claimed.

## What was used

| Item | How it was used |
| --- | --- |
| **APIMatic-generated PayPal Server SDK for Python** (`paypal` v2.29, MIT, from `github.com/context-plugins/paypal-python-sdk` at commit `143e57f2`) | Every PayPal REST call in the product (create / get / capture order, get capture, refund capture, get refund) goes through this SDK, in `app/integrations/paypal/gateway.py`. Vendored as an unmodified wheel in `backend/vendor/` for Docker builds |
| **APIMatic PayPal Context Plugin** skills (`python-integrate-paypal`, `python-getting-started`, client initialization, authentication, calling endpoints, models, error handling, configuration and resilience, testing) | Used while building, to look up the SDK contract instead of guessing: signatures, keyword-only parameters, `Dict` request companions, `UNSET` vs `None`, the error union per operation, retry defaults, timeout semantics and the transport test seam. The results are written down in [`paypal-plan.md`](../paypal-plan.md) |
| SDK map shipped with the SDK (`sdk-map.md`, `map/operations/*.md`) | Source for every row of the contract sheet |

## What was not used

- We did **not** use APIMatic to generate an SDK for SupportFlow's own API. The frontend calls the backend with a small typed `fetch` wrapper (`frontend/src/lib/api.ts`).
- We did **not** use the TypeScript or .NET PayPal SDKs. PayPal is only called from the backend.
- **Webhook signature verification is not in the generated SDK**, so it calls PayPal's documented `POST /v1/notifications/verify-webhook-signature` directly with `httpx` (`app/integrations/paypal/webhook_verify.py`). This part was written from PayPal's public REST docs, not from an APIMatic lookup.
- No APIMatic hosted portal, API transformer or code-generation service was run as part of this project.

## How the SDK is wired

| Concern | Choice | Where |
| --- | --- | --- |
| Client | Sync `PaypalClient`, one per process, built lazily, closed on shutdown | `app/integrations/paypal/client.py` |
| Auth | `ClientCredentials(client_id, client_secret)`; the SDK manages and caches the OAuth token | same |
| Base URL | always passed explicitly from `PAYPAL_BASE_URL` (Sandbox by default) | same |
| Timeouts | `PAYPAL_TIMEOUT_SECONDS` (20 s) per wait | same |
| Retries | SDK default for idempotent reads; POSTs are not retried by the SDK and are made safe with `PayPal-Request-Id` | gateway |
| Requests | built as the SDK's `…Dict` TypedDicts, omitting optional keys rather than sending `None` | gateway |
| Errors | one translation ladder: `OAuthProviderError` → auth error; typed `Error` arm → rejected with name, message, debug id; `RawError` → status-based; transport errors split into "never sent" vs "outcome unknown"; decode failures on writes → outcome unknown | `app/integrations/paypal/errors.py` |
| Testing | the SDK's documented transport seam (`use_transport_for_tests`), so the real SDK builds and parses every message | `backend/tests/paypal_stub.py` |

## Known limitations

- The SDK's error model requires `debug_id`. A PayPal 4xx body without it fails to decode; on writes we treat that as
  *outcome unknown* (safe) rather than as a clean rejection. Covered by a test.
- `str(ApiError)` does not include the body, so the error ladder logs the typed fields explicitly (never credentials).
